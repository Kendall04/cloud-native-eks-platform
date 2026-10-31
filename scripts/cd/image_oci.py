"""Source-bound OCI export/import. Pure file validation; no AWS SDK or credentials."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[2]
SERVICES=('auth','shipment','tracking')
INDEX='application/vnd.oci.image.index.v1+json'
MANIFEST='application/vnd.oci.image.manifest.v1+json'
CONFIG='application/vnd.oci.image.config.v1+json'
LAYER='application/vnd.oci.image.layer.v1.tar+gzip'
CHUNK=1024*1024
MAX_ARCHIVE=2*1024**3
MAX_EXPANDED=2*1024**3
MAX_LAYER_MEMBERS=100000


def require(ok,message):
    if not ok:raise ValueError(message)


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(data):return hashlib.sha256(data).hexdigest()


def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def load(data):return json.loads(data,object_pairs_hook=pairs)


def safe_name(name):
    require(isinstance(name,str) and name and '\\' not in name and ':' not in name and '\x00' not in name,'Unsafe path')
    p=PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts and str(p)==name,'Unsafe path')
    return name


def source_manifest(root,service,commit):
    """Only the Windows/reviewed checkout asserts Git provenance; VM checks bytes."""
    root=Path(root)
    require(service in SERVICES and re.fullmatch('[0-9a-f]{40}',commit),'Invalid source selection')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==commit,'Wrong reviewed source commit')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip(),'Clean reviewed checkout required')
    context=root/'microservices'/f'{service}-service'
    tracked=subprocess.check_output(['git','ls-files','-z','--',str(context.relative_to(root)).replace('\\','/')],cwd=root).split(b'\0')
    files={};total=0
    for entry in tracked:
        if not entry:continue
        path=root/entry.decode();relative=safe_name(path.relative_to(context).as_posix())
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(context.resolve()),'Source symlink/outside context')
        size=path.stat().st_size;total+=size
        require(size<=2*1024**2 and total<=32*1024**2 and len(files)<2048,'Source context limit')
        files[relative]={'sha256':digest(path.read_bytes()),'bytes':size}
    require('Dockerfile' in files and len(files)>1,'Incomplete tracked build context')
    return {'schemaVersion':1,'service':service,'sourceCommit':commit,'platform':'linux/amd64','files':files}


def validate_source(value):
    require(set(value)=={'schemaVersion','service','sourceCommit','platform','files'} and value['schemaVersion']==1,'Source manifest shape')
    require(value['service'] in SERVICES and re.fullmatch('[0-9a-f]{40}',value['sourceCommit']) and value['platform']=='linux/amd64','Source manifest scope')
    require(isinstance(value['files'],dict) and 1<len(value['files'])<=2048 and 'Dockerfile' in value['files'],'Source files required')
    total=0
    for name,row in value['files'].items():
        safe_name(name);require(set(row)=={'sha256','bytes'} and re.fullmatch('[0-9a-f]{64}',row['sha256']) and type(row['bytes']) is int and 0<=row['bytes']<=2*1024**2,'Source descriptor invalid')
        total+=row['bytes']
    require(total<=32*1024**2,'Source context limit')


def build_offline(source,source_sha,source_root,output,builder,builder_state):
    """Uses an existing running local OCI-capable builder; never bootstraps one."""
    require(sys.platform.startswith('linux') and Path('/dev/shm').is_dir(),'Linux/tmpfs required for build only')
    require(re.fullmatch('[0-9a-f]{64}',source_sha),'Expected source manifest SHA required')
    raw=Path(source).read_bytes();require(digest(raw)==source_sha,'Source manifest integrity mismatch');m=load(raw);validate_source(m)
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',builder),'Existing local builder name required')
    state=Path(builder_state);require(state.is_dir() and not state.is_symlink(),'Existing Buildx metadata directory required')
    out=Path(output);require(out.name.endswith('.oci.tar') and not out.exists(),'New OCI output required')
    base=Path(source_root).resolve()
    # No existing Docker credential/config file is read. Builder metadata is an
    # explicit separate input; remote/TLS contexts and insecure builders reject.
    with tempfile.TemporaryDirectory(prefix='cnp-build-authless-',dir='/dev/shm') as config, tempfile.TemporaryDirectory(prefix='cnp-context-') as context:
        env={k:os.environ[k] for k in ('PATH','HOME','LANG','LC_ALL','TMPDIR') if k in os.environ}
        env.update(DOCKER_CONFIG=config,BUILDX_CONFIG=str(state.resolve()))
        info=subprocess.check_output(['docker','buildx','inspect',builder],env=env,text=True)
        require(re.findall(r'(?m)^Driver:\s*(\S+)',info)==['docker-container'],'Existing docker-container OCI builder required')
        require(re.findall(r'(?m)^Endpoint:\s*(\S+)',info)==['unix:///var/run/docker.sock'],'Local Unix builder only')
        require(re.findall(r'(?m)^Status:\s*(\S+)',info)==['running'] and '--allow-insecure-entitlement' not in info,'Running restricted builder required')
        for name,row in m['files'].items():
            p=base/name;require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(base),'Source path mismatch')
            data=p.read_bytes();require(len(data)==row['bytes'] and digest(data)==row['sha256'],'Source file mismatch')
            target=Path(context)/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        subprocess.run(['docker','buildx','build','--builder',builder,'--platform','linux/amd64','--provenance=false','--sbom=false',
            '--label','org.opencontainers.image.revision='+m['sourceCommit'],'--label','io.cnp.source-manifest-sha256='+source_sha,
            '--label','io.cnp.service='+m['service'],'--build-arg','SOURCE_COMMIT='+m['sourceCommit'],
            '--output','type=oci,oci-mediatypes=true,compression=gzip,dest='+str(out.resolve()),'-f',str(Path(context)/'Dockerfile'),context],env=env,check=True)
    return {'service':m['service'],'sourceCommit':m['sourceCommit'],'sourceManifestSha256':source_sha,'archiveSha256':file_sha(out),'producer':'LOCAL_BUILD_NO_AWS','githubActionsVerified':False}


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk:=f.read(CHUNK):h.update(chunk)
    return h.hexdigest()


def validate_layer_tar(stream,expanded_size,last_nonzero):
    """Parse only: no extraction, link following, device creation or file writes."""
    headers=0;depth=0
    class LayerInfo(tarfile.TarInfo):
        def _proc_member(self,archive):
            # Both legacy and current tarfile readers dispatch here before
            # reading metadata payloads, including recursively nested headers.
            # New CPython readers bypass the public frombuf/fromtarfile hooks.
            nonlocal headers,depth
            headers+=1;depth+=1
            try:
                # This hook counts decoded headers, not the terminating zero
                # block counted by the old reader hook; the member cap is equal.
                require(headers<=MAX_LAYER_MEMBERS and depth<=16,'Layer TAR metadata/member limit')
                require(0<=self.size<=MAX_EXPANDED,'Layer TAR size limit')
                if self.type in (tarfile.XHDTYPE,tarfile.XGLTYPE,tarfile.SOLARIS_XHDTYPE,tarfile.GNUTYPE_LONGNAME,tarfile.GNUTYPE_LONGLINK):
                    require(self.size<=CHUNK,'Layer TAR metadata size limit')
                require(self.type!=tarfile.GNUTYPE_SPARSE,'Layer TAR sparse format unsupported')
                return super()._proc_member(archive)
            finally:depth-=1

        def _reject_sparse(self,*_):raise ValueError('Layer TAR sparse format unsupported')
        _proc_gnusparse_00=_reject_sparse
        _proc_gnusparse_01=_reject_sparse
        _proc_gnusparse_10=_reject_sparse

    try:
        with tarfile.open(fileobj=stream,mode='r|',tarinfo=LayerInfo) as archive:
            count=0;declared=0
            for item in archive:
                count+=1;declared+=item.size
                require(count<=MAX_LAYER_MEMBERS and 0<=item.size<=MAX_EXPANDED and declared<=MAX_EXPANDED,'Layer TAR member/size limit')
                name=item.name;path=PurePosixPath(name)
                require(name and '\x00' not in name and '\\' not in name and not re.match(r'^[A-Za-z]:',name) and not path.is_absolute() and '..' not in path.parts,'Layer TAR unsafe member path')
                require(path.parts or item.isdir(),'Layer TAR root must be a directory')
                require(not item.issparse() and item.type in (tarfile.REGTYPE,tarfile.AREGTYPE,tarfile.DIRTYPE,tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.BLKTYPE,tarfile.FIFOTYPE),'Layer TAR unsupported member')
                if not item.isfile():require(item.size==0,'Layer TAR non-file payload')
                if item.issym() or item.islnk():
                    target=item.linkname
                    require(target and '\x00' not in target and '\\' not in target and not re.match(r'^[A-Za-z]:',target),'Layer TAR invalid link target')
                    # Absolute symlinks are image-root paths, never host paths.
                    # Hardlink names are rooted at the archive, not member.parent.
                    parts=[] if target.startswith('/') or item.islnk() else list(path.parent.parts)
                    for part in PurePosixPath(target).parts:
                        if part in ('/','.'):continue
                        if part=='..':
                            require(parts,'Layer TAR link escapes image root');parts.pop()
                        else:parts.append(part)
            end=archive.offset
        require(expanded_size%tarfile.BLOCKSIZE==0 and expanded_size-end>=2*tarfile.BLOCKSIZE and last_nonzero<end,'Layer TAR missing terminator or trailing content')
    except (tarfile.TarError,EOFError) as error:
        raise ValueError('Layer TAR invalid structure') from error


class Image:
    """Strict single-image OCI subset; no extraction, external URLs or config read."""
    def __init__(self,path,expected_sha,service,commit,source_sha):
        self.path=Path(path);self.file=None;self.tar=None
        require(self.path.name.endswith('.oci.tar') and not self.path.is_symlink(),'OCI archive path required')
        require(service in SERVICES and re.fullmatch('[0-9a-f]{40}',commit) and re.fullmatch('[0-9a-f]{64}',source_sha) and re.fullmatch('[0-9a-f]{64}',expected_sha),'Explicit image bindings required')
        self.archive_sha=expected_sha;self.service=service;self.commit=commit
        try:
            self.file=self.path.open('rb');self.stat=os.fstat(self.file.fileno())
            require(0<self.stat.st_size<=MAX_ARCHIVE,'Archive size limit');h=hashlib.sha256()
            while chunk:=self.file.read(CHUNK):h.update(chunk)
            require(h.hexdigest()==expected_sha,'Archive integrity mismatch');self.unchanged();self.file.seek(0)
            self.tar=tarfile.open(fileobj=self.file,mode='r:')
            members=[]
            for member in self.tar:
                require(len(members)<512,'OCI member limit');members.append(member)
            self.members={};total=0
            for item in members:
                name=item.name.rstrip('/') if item.isdir() else item.name;safe_name(name)
                if item.isdir():require(name in ('blobs','blobs/sha256'),'Unexpected OCI directory');continue
                require(item.isfile() and not item.issparse() and name not in self.members,'OCI link/duplicate/non-file')
                require(name in ('oci-layout','index.json') or re.fullmatch(r'blobs/sha256/[0-9a-f]{64}',name),'Unexpected OCI file')
                total+=item.size;require(0<=item.size<=MAX_ARCHIVE and total<=MAX_ARCHIVE,'OCI expanded size limit');self.members[name]=item
            self.file.seek(self.tar.offset)
            while tail:=self.file.read(CHUNK):require(not tail.strip(b'\x00'),'Unexpected data after OCI tar end')
            require(load(self.small('oci-layout'))=={'imageLayoutVersion':'1.0.0'},'OCI layout version')
            index=load(self.small('index.json'));require(index.get('schemaVersion')==2 and index.get('mediaType',INDEX)==INDEX and len(index.get('manifests',[]))==1,'Single OCI image required')
            desc=index['manifests'][0];self.manifest_bytes=self.blob(desc,MANIFEST,small=True);self.manifest_digest=desc['digest'];manifest=load(self.manifest_bytes)
            require(set(manifest)<= {'schemaVersion','mediaType','config','layers','annotations'} and manifest.get('schemaVersion')==2 and manifest.get('mediaType')==MANIFEST,'Image manifest shape')
            config=load(self.blob(manifest['config'],CONFIG,small=True));labels=config.get('config',{}).get('Labels',{})
            require(config.get('os')=='linux' and config.get('architecture')=='amd64' and not config.get('variant'),'Image platform mismatch')
            platform=desc.get('platform',{});require(not platform or platform=={'os':'linux','architecture':'amd64'},'Index platform mismatch')
            require(labels.get('org.opencontainers.image.revision')==commit and labels.get('io.cnp.source-manifest-sha256')==source_sha and labels.get('io.cnp.service')==service,'Image source binding mismatch')
            layers=manifest.get('layers',[]);diffs=config.get('rootfs',{}).get('diff_ids',[])
            require(config.get('rootfs',{}).get('type')=='layers' and 0<len(layers)<=128 and len(diffs)==len(layers),'Rootfs coverage mismatch')
            self.blobs=[manifest['config']]+layers
            expected={'oci-layout','index.json','blobs/sha256/'+self.manifest_digest.split(':')[1]}
            for descriptor in self.blobs:expected.add(self.blob_name(descriptor))
            require(set(self.members)==expected,'Missing/unreferenced OCI blobs')
            expanded_total=0
            for descriptor,diff in zip(layers,diffs):
                self.blob(descriptor,LAYER)
                require(re.fullmatch('sha256:[0-9a-f]{64}',diff),'Invalid rootfs digest')
                h=hashlib.sha256();size=0;last_nonzero=-1
                with self.open_blob(descriptor) as compressed, gzip.GzipFile(fileobj=compressed) as stream:
                    while chunk:=stream.read(CHUNK):
                        content=chunk.rstrip(b'\x00')
                        if content:last_nonzero=size+len(content)-1
                        size+=len(chunk);expanded_total+=len(chunk);require(expanded_total<=MAX_EXPANDED,'Layer decompression limit');h.update(chunk)
                require('sha256:'+h.hexdigest()==diff,'Rootfs diff digest mismatch')
                with self.open_blob(descriptor) as compressed, gzip.GzipFile(fileobj=compressed) as stream:
                    validate_layer_tar(stream,size,last_nonzero)
        except BaseException:
            self.close();raise

    def small(self,name):
        require(name in self.members and self.members[name].size<=2*1024**2,'Missing/oversized OCI JSON')
        return self.tar.extractfile(self.members[name]).read()

    def blob_name(self,d):
        require(isinstance(d,dict) and not set(d)&{'urls','data'} and re.fullmatch('sha256:[0-9a-f]{64}',d.get('digest','')) and type(d.get('size')) is int and d['size']>0,'Invalid/external blob descriptor')
        return 'blobs/sha256/'+d['digest'].split(':')[1]

    @contextmanager
    def open_blob(self,d):
        self.unchanged();name=self.blob_name(d);require(name in self.members and self.members[name].size==d['size'],'Blob size/missing mismatch')
        with self.tar.extractfile(self.members[name]) as stream:yield stream

    def blob(self,d,media,small=False):
        require(d.get('mediaType')==media,'Unsupported OCI media type');h=hashlib.sha256()
        with self.open_blob(d) as stream:
            if small:
                require(d['size']<=2*1024**2,'OCI JSON too large');data=stream.read();h.update(data)
            else:
                while chunk:=stream.read(CHUNK):h.update(chunk)
                data=None
        require('sha256:'+h.hexdigest()==d['digest'],'Blob digest mismatch');return data

    def unchanged(self):
        current=os.fstat(self.file.fileno())
        require((current.st_ino,current.st_size,current.st_mtime_ns)==(self.stat.st_ino,self.stat.st_size,self.stat.st_mtime_ns),'Archive changed after validation')

    def close(self):
        if self.tar:self.tar.close()
        if self.file:self.file.close()

    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['prepare','build']);p.add_argument('--service',choices=SERVICES);p.add_argument('--commit');p.add_argument('--source',type=Path);p.add_argument('--sha256');p.add_argument('--source-root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--builder');p.add_argument('--builder-state',type=Path);a=p.parse_args()
    if a.operation=='prepare':
        data=canonical(source_manifest(ROOT,a.service,a.commit));a.output.open('xb').write(data);print(json.dumps({'sourceManifestSha256':digest(data),'bytes':len(data)}))
    else:print(json.dumps(build_offline(a.source,a.sha256,a.source_root,a.output,a.builder,a.builder_state)))

if __name__=='__main__':main()
