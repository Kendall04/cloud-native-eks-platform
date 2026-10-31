"""Synthetic OCI fixtures and offline builder tests. Standard library only."""
import copy
import gzip
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cd'))
import image_oci as o

COMMIT='a'*40
SOURCE='b'*64


def layer_tar(payload=b'synthetic layer only\n',members=None):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        if members is None:
            item=tarfile.TarInfo('app/synthetic.txt');item.size=len(payload);tar.addfile(item,io.BytesIO(payload))
        else:
            for item,data in members:tar.addfile(item,io.BytesIO(data) if data is not None else None)
    return stream.getvalue()


def fixture(service='auth',source=SOURCE,change=None,payload=b'synthetic layer only\n',raw_layer=None):
    payload=layer_tar(payload) if raw_layer is None else raw_layer
    layer=gzip.compress(payload,mtime=0)
    config={'architecture':'amd64','os':'linux','config':{'Labels':{
        'org.opencontainers.image.revision':COMMIT,'io.cnp.service':service,
        'io.cnp.source-manifest-sha256':source}},'rootfs':{'type':'layers','diff_ids':['sha256:'+o.digest(payload)]}}
    if change:change(config)
    raw=o.canonical(config)
    descriptor=lambda data,media:{'mediaType':media,'digest':'sha256:'+o.digest(data),'size':len(data)}
    manifest=o.canonical({'schemaVersion':2,'mediaType':o.MANIFEST,'config':descriptor(raw,o.CONFIG),'layers':[descriptor(layer,o.LAYER)]})
    return {'oci-layout':o.canonical({'imageLayoutVersion':'1.0.0'}),
        'index.json':o.canonical({'schemaVersion':2,'mediaType':o.INDEX,'manifests':[descriptor(manifest,o.MANIFEST)]}),
        'blobs/sha256/'+o.digest(manifest):manifest,'blobs/sha256/'+o.digest(raw):raw,'blobs/sha256/'+o.digest(layer):layer}


def archive(path,files,extra=None):
    with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as tar:
        for name,data in files.items():
            item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
        if extra:
            item,data=extra;tar.addfile(item,io.BytesIO(data) if data is not None else None)
    return o.file_sha(path)


class OCIValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'image.oci.tar'

    def image(self,files=None,**kwargs):
        h=archive(self.path,files or fixture(),**kwargs)
        return o.Image(self.path,h,'auth',COMMIT,SOURCE)

    def test_valid_graph_has_exact_config_layer_and_manifest(self):
        with self.image() as image:
            self.assertEqual(2,len(image.blobs))
            self.assertEqual('sha256:'+o.digest(image.manifest_bytes),image.manifest_digest)
            for d in image.blobs:
                with image.open_blob(d) as stream:self.assertEqual(d['size'],len(stream.read()))
        self.assertEqual(['image.oci.tar'],[x.name for x in self.path.parent.iterdir()])

    def test_archive_sha_rejects_modification(self):
        h=archive(self.path,fixture());self.path.write_bytes(self.path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'integrity'):o.Image(self.path,h,'auth',COMMIT,SOURCE)

    def test_rehashed_archive_rejects_hidden_tail(self):
        archive(self.path,fixture());self.path.write_bytes(self.path.read_bytes()+b'hidden')
        with self.assertRaisesRegex(ValueError,'after OCI'):o.Image(self.path,o.file_sha(self.path),'auth',COMMIT,SOURCE)

    def test_blob_tampering_rejects_even_with_new_archive_sha(self):
        files=fixture();key=next(k for k,v in files.items() if v[:2]==b'\x1f\x8b');files[key]=files[key][:-1]+b'!'
        with self.assertRaisesRegex(ValueError,'digest'):self.image(files)

    def test_gzip_non_tar_rejected_despite_consistent_hashes_and_labels(self):
        with self.assertRaisesRegex(ValueError,'Layer TAR'):
            with self.image(fixture(raw_layer=b'not a tar archive')):pass

    def test_layer_tar_checksum_truncation_terminator_and_hidden_content_reject(self):
        good=layer_tar(b'x'*2048)
        bad_checksum=b'!'+good[1:]
        for raw in (bad_checksum,good[:1024],good[:512+2048],good+b'nonzero hidden content',good[:512+2048]+b'\x00'*512):
            with self.subTest(size=len(raw)),self.assertRaisesRegex(ValueError,'Layer TAR'):
                with self.image(fixture(raw_layer=raw)):pass

    def test_layer_tar_paths_links_and_member_limits_reject_without_extraction(self):
        for name,kind,target in (('../escape',tarfile.REGTYPE,''),('/absolute',tarfile.REGTYPE,''),('C:/escape',tarfile.REGTYPE,''),('app/link',tarfile.SYMTYPE,'../../escape'),('app/link',tarfile.LNKTYPE,'../escape')):
            member=tarfile.TarInfo(name);member.type=kind;member.linkname=target;member.size=0
            with self.subTest(name=name,kind=kind),self.assertRaisesRegex(ValueError,'Layer TAR'):
                with self.image(fixture(raw_layer=layer_tar(members=[(member,b'')]))):pass
        members=[(tarfile.TarInfo('app/'+str(i)),b'') for i in range(3)]
        with patch.object(o,'MAX_LAYER_MEMBERS',2),self.assertRaisesRegex(ValueError,'member.*limit'):
            with self.image(fixture(raw_layer=layer_tar(members=members))):pass

    def test_real_layer_tar_allows_image_root_and_relative_links_without_following_them(self):
        directory=tarfile.TarInfo('.');directory.type=tarfile.DIRTYPE
        file=tarfile.TarInfo('usr/lib/synthetic');file.size=4
        absolute=tarfile.TarInfo('lib');absolute.type=tarfile.SYMTYPE;absolute.linkname='/usr/lib'
        relative=tarfile.TarInfo('usr/lib/alias');relative.type=tarfile.SYMTYPE;relative.linkname='../lib/synthetic'
        hard=tarfile.TarInfo('usr/lib/hard');hard.type=tarfile.LNKTYPE;hard.linkname='usr/lib/synthetic'
        with self.image(fixture(raw_layer=layer_tar(members=[(directory,None),(file,b'data'),(absolute,None),(relative,None),(hard,None)]))):pass
        self.assertEqual(['image.oci.tar'],[x.name for x in self.path.parent.iterdir()])

    def test_real_layer_tar_supports_long_pax_and_gnu_names(self):
        for format in (tarfile.PAX_FORMAT,tarfile.GNU_FORMAT):
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w',format=format) as tar:
                member=tarfile.TarInfo('usr/share/'+('long-component/'*12)+'synthetic');member.size=4
                tar.addfile(member,io.BytesIO(b'data'))
            with self.subTest(format=format),self.image(fixture(raw_layer=stream.getvalue())):pass

    def test_layer_metadata_is_bounded_before_parser_allocation_and_sparse_processing(self):
        header=tarfile.TarInfo('pax');header.type=tarfile.XHDTYPE;header.size=o.CHUNK+1
        with self.assertRaisesRegex(ValueError,'metadata size limit'):
            with self.image(fixture(raw_layer=layer_tar(members=[(header,b'x'*header.size)]))):pass
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w',format=tarfile.PAX_FORMAT) as tar:
            item=tarfile.TarInfo('app/file');item.size=4;item.pax_headers={'GNU.sparse.major':'1','GNU.sparse.minor':'0'}
            tar.addfile(item,io.BytesIO(b'data'))
        with self.assertRaisesRegex(ValueError,'sparse format'):
            with self.image(fixture(raw_layer=stream.getvalue())):pass
        payload=b'12 key=data\n';self.assertEqual(12,len(payload))
        headers=[]
        for i in range(17):
            item=tarfile.TarInfo('pax'+str(i));item.type=tarfile.XHDTYPE;item.size=len(payload);headers.append((item,payload))
        with self.assertRaisesRegex(ValueError,'metadata/member limit'):
            with self.image(fixture(raw_layer=layer_tar(members=headers))):pass

    def test_valid_oversized_pax_metadata_rejects(self):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w',format=tarfile.PAX_FORMAT) as tar:
            item=tarfile.TarInfo('app/synthetic.txt');item.size=4
            item.pax_headers={'comment':'x'*(o.CHUNK+1)}
            tar.addfile(item,io.BytesIO(b'data'))
        raw=stream.getvalue()
        self.assertGreater(tarfile.TarInfo.frombuf(raw[:512],'utf-8','strict').size,o.CHUNK)
        with self.assertRaisesRegex(ValueError,'metadata size limit'):
            with self.image(fixture(raw_layer=raw)):pass

    def test_metadata_bounds_precede_all_pax_and_gnu_payload_parsers(self):
        for kind in (tarfile.XHDTYPE,tarfile.XGLTYPE,tarfile.SOLARIS_XHDTYPE,
                     tarfile.GNUTYPE_LONGNAME,tarfile.GNUTYPE_LONGLINK):
            header=tarfile.TarInfo('metadata');header.type=kind;header.size=o.CHUNK+1
            raw=layer_tar(members=[(header,b'x'*header.size)])
            with self.subTest(kind=kind),patch.object(tarfile.TarInfo,'_proc_pax') as pax,patch.object(tarfile.TarInfo,'_proc_gnulong') as gnu:
                with self.assertRaisesRegex(ValueError,'metadata size limit'):
                    with self.image(fixture(raw_layer=raw)):pass
                pax.assert_not_called();gnu.assert_not_called()

    def test_valid_pax_metadata_at_exact_limit_is_accepted(self):
        prefix=str(o.CHUNK).encode()+b' comment='
        payload=prefix+b'x'*(o.CHUNK-len(prefix)-1)+b'\n'
        self.assertEqual(o.CHUNK,len(payload))
        header=tarfile.TarInfo('pax');header.type=tarfile.XHDTYPE;header.size=len(payload)
        member=tarfile.TarInfo('app/synthetic.txt');member.size=4
        with self.image(fixture(raw_layer=layer_tar(members=[(header,payload),(member,b'data')]))):pass

    def test_metadata_headers_share_the_member_budget(self):
        payload=b'12 key=data\n'
        header=tarfile.TarInfo('pax');header.type=tarfile.XHDTYPE;header.size=len(payload)
        member=tarfile.TarInfo('app/synthetic.txt');member.size=4
        raw=layer_tar(members=[(header,payload),(member,b'data')])
        with patch.object(o,'MAX_LAYER_MEMBERS',2),self.image(fixture(raw_layer=raw)):pass
        with patch.object(o,'MAX_LAYER_MEMBERS',1),self.assertRaisesRegex(ValueError,'metadata/member limit'):
            with self.image(fixture(raw_layer=raw)):pass

    def test_metadata_nesting_accepts_exact_depth_and_rejects_next_header(self):
        payload=b'12 key=data\n';headers=[]
        for i in range(16):
            item=tarfile.TarInfo('pax'+str(i));item.type=tarfile.XHDTYPE;item.size=len(payload)
            headers.append((item,payload))
        member=tarfile.TarInfo('app/synthetic.txt');member.size=4
        with self.image(fixture(raw_layer=layer_tar(members=headers[:15]+[(member,b'data')]))):pass
        with self.assertRaisesRegex(ValueError,'metadata/member limit'):
            with self.image(fixture(raw_layer=layer_tar(members=headers+[(member,b'data')]))):pass

    def test_missing_and_unreferenced_files_reject(self):
        for missing in (True,False):
            files=fixture()
            if missing:files.pop(next(k for k in files if k.startswith('blobs/')))
            else:files['blobs/sha256/'+'f'*64]=b'unreferenced'
            with self.subTest(missing=missing),self.assertRaises(ValueError):self.image(files)

    def test_member_count_is_bounded_before_collecting_the_whole_archive(self):
        files={'blobs/sha256/'+format(i,'064x'):b'x' for i in range(513)}
        with self.assertRaisesRegex(ValueError,'member limit'):self.image(files)

    def test_links_duplicates_and_paths_reject(self):
        for name,kind in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('blobs\\escape',tarfile.REGTYPE),
                          ('index.json',tarfile.REGTYPE),('blobs/sha256/'+'f'*64,tarfile.SYMTYPE),('blobs/sha256/'+'f'*64,tarfile.LNKTYPE)]:
            item=tarfile.TarInfo(name);item.type=kind;item.linkname='outside';item.size=0
            with self.subTest(name=name,kind=kind),self.assertRaises(ValueError):self.image(extra=(item,b'' if kind==tarfile.REGTYPE else None))

    def test_platform_source_and_rootfs_mismatch_reject(self):
        changes=[lambda c:c.update(os='windows'),lambda c:c.update(architecture='arm64'),lambda c:c.update(variant='v8'),
                 lambda c:c['config']['Labels'].update({'org.opencontainers.image.revision':'c'*40}),
                 lambda c:c['config']['Labels'].update({'io.cnp.service':'tracking'}),
                 lambda c:c['config']['Labels'].update({'io.cnp.source-manifest-sha256':'d'*64}),
                 lambda c:c['rootfs'].update(diff_ids=['sha256:'+'e'*64])]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):self.image(fixture(change=change))

    def test_external_descriptor_multiarch_duplicate_json_reject(self):
        for mode in ('url','multi','platform','duplicate'):
            files=fixture();index=json.loads(files['index.json'])
            if mode=='url':index['manifests'][0]['urls']=['https://external.invalid/blob']
            elif mode=='multi':index['manifests']*=2
            elif mode=='platform':index['manifests'][0]['platform']={'os':'linux','architecture':'arm64'}
            files['index.json']=b'{"schemaVersion":2,"schemaVersion":2}' if mode=='duplicate' else o.canonical(index)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.image(files)

    def test_bounded_decompression_and_changed_open_file_reject(self):
        with patch.object(o,'MAX_EXPANDED',8),self.assertRaisesRegex(ValueError,'decompression'):self.image()
        with self.image() as image:
            with self.path.open('ab') as f:f.write(b'changed')
            with self.assertRaisesRegex(ValueError,'changed'):image.unchanged()


class OfflineBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.context=self.root/'source';self.context.mkdir();(self.context/'Dockerfile').write_bytes(b'FROM scratch\n');(self.context/'app.txt').write_bytes(b'synthetic')
        self.state=self.root/'existing-buildx';self.state.mkdir()
        self.source=self.root/'source.json';self.output=self.root/'image.oci.tar'
        self.manifest={'schemaVersion':1,'service':'auth','sourceCommit':COMMIT,'platform':'linux/amd64',
            'files':{p.name:{'bytes':p.stat().st_size,'sha256':o.file_sha(p)} for p in self.context.iterdir()}}
        self.raw=o.canonical(self.manifest);self.source.write_bytes(self.raw)

    def run_build(self):return o.build_offline(self.source,o.digest(self.raw),self.context,self.output,'local-reviewed',self.state)

    def test_non_linux_fails_before_docker(self):
        with patch.object(o.sys,'platform','win32'),patch.object(o.subprocess,'check_output') as call,self.assertRaisesRegex(ValueError,'Linux'):
            self.run_build()
        call.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith('linux'),'Real Linux tmpfs harness runs over SSH')
    def test_build_sanitizes_credentials_and_transfers_only_bound_files(self):
        (self.context/'untracked-secret.txt').write_bytes(b'synthetic must not be copied')
        def build(args,**kwargs):
            env=kwargs['env'];self.assertFalse(any(k.startswith(('AWS_','GH_')) for k in env));self.assertNotIn('DOCKER_HOST',env)
            self.assertEqual([],list(Path(env['DOCKER_CONFIG']).iterdir()))
            copied=Path(args[-1]);self.assertEqual({'Dockerfile','app.txt'},{p.name for p in copied.iterdir()})
            self.assertNotIn('--push',args);self.assertIn('--provenance=false',args)
            archive(self.output,fixture(source=o.digest(self.raw)))
        info='Driver: docker-container\nEndpoint: unix:///var/run/docker.sock\nStatus: running\n'
        with patch.dict(os.environ,{'AWS_SECRET_ACCESS_KEY':'synthetic','GH_TOKEN':'synthetic','DOCKER_CONFIG':'denied-path','DOCKER_HOST':'remote'}), \
             patch.object(o.subprocess,'check_output',return_value=info) as inspect,patch.object(o.subprocess,'run',side_effect=build) as command:
            receipt=self.run_build()
        self.assertEqual(1,inspect.call_count);self.assertEqual(1,command.call_count);self.assertFalse(receipt['githubActionsVerified'])
        with o.Image(self.output,receipt['archiveSha256'],'auth',COMMIT,o.digest(self.raw)):pass

    @unittest.skipUnless(sys.platform.startswith('linux'),'Real Linux tmpfs harness runs over SSH')
    def test_remote_stopped_insecure_wrong_driver_and_changed_source_do_not_build(self):
        bad=['Driver: docker\nEndpoint: unix:///var/run/docker.sock\nStatus: running\n',
             'Driver: docker-container\nEndpoint: tcp://remote\nStatus: running\n',
             'Driver: docker-container\nEndpoint: unix:///var/run/docker.sock\nStatus: stopped\n',
             'Driver: docker-container\nEndpoint: unix:///var/run/docker.sock\nStatus: running\nFlags: --allow-insecure-entitlement security.insecure\n']
        for info in bad:
            with self.subTest(info=info),patch.object(o.subprocess,'check_output',return_value=info),patch.object(o.subprocess,'run') as run,self.assertRaises(ValueError):self.run_build()
            run.assert_not_called()
        (self.context/'app.txt').write_bytes(b'changed')
        with patch.object(o.subprocess,'check_output',return_value='Driver: docker-container\nEndpoint: unix:///var/run/docker.sock\nStatus: running\n'),patch.object(o.subprocess,'run') as run,self.assertRaisesRegex(ValueError,'mismatch'):self.run_build()
        run.assert_not_called()

    def test_source_paths_hashes_and_missing_manifest_reject(self):
        for change in (lambda m:m['files'].update({'../escape':{'sha256':'a'*64,'bytes':1}}),lambda m:m.update(platform='linux/arm64'),lambda m:m['files'].pop('Dockerfile')):
            value=copy.deepcopy(self.manifest);change(value)
            with self.assertRaises(ValueError):o.validate_source(value)

    def test_prepare_requires_clean_reviewed_git_and_exact_tracked_files(self):
        context=self.root/'microservices/auth-service';context.mkdir(parents=True)
        for p in self.context.iterdir():(context/p.name).write_bytes(p.read_bytes())
        tracked=b'microservices/auth-service/Dockerfile\0microservices/auth-service/app.txt\0'
        with patch.object(o.subprocess,'check_output',side_effect=[COMMIT,'',tracked]):
            actual=o.source_manifest(self.root,'auth',COMMIT)
        self.assertEqual(self.manifest,actual)
        with patch.object(o.subprocess,'check_output',side_effect=[COMMIT,' M app.txt']),self.assertRaisesRegex(ValueError,'Clean'):
            o.source_manifest(self.root,'auth',COMMIT)


if __name__=='__main__':unittest.main()
