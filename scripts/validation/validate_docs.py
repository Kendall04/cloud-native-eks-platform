"""Check repository Markdown local links/anchors and code-fence structure; no network/AWS."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def markdown_files(root):
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root,
    ).decode().split('\0')
    return sorted({root / name for name in names if name.endswith('.md') and (root / name).is_file()})


def prose(text):
    """Replace fenced blocks with blank lines while preserving source line numbers."""
    fence = None
    output = []
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            token = match[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            output.append('')
        else:
            output.append('' if fence else line)
    if fence:
        raise ValueError('Unclosed Markdown code fence')
    return '\n'.join(output)


def anchors(text):
    result, seen = set(), {}
    for line in prose(text).splitlines():
        match = re.match(r'^#{1,6}\s+(.+?)(?:\s+#+)?$', line)
        if not match:
            continue
        title = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', match[1]).lower()
        slug = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        index = seen.get(slug, 0)
        seen[slug] = index + 1
        result.add(slug + (f'-{index}' if index else ''))
    return result


def validate(root=ROOT):
    errors, links, diagrams = [], 0, 0
    files = markdown_files(root)
    for path in files:
        text = path.read_text(encoding='utf-8-sig')
        diagrams += len(re.findall(r'^```mermaid\s*$', text, re.M))
        try:
            body = prose(text)
        except ValueError as error:
            errors.append(f'{path.relative_to(root)}: {error}')
            continue
        for number, line in enumerate(body.splitlines(), 1):
            # Inline code may document placeholder paths; it is not a hyperlink.
            line = re.sub(r'`[^`]+`', '', line)
            for match in re.finditer(r'!?\[[^\]]*\]\(([^)]+)\)', line):
                href = match[1].strip().split(' "', 1)[0].strip('<>')
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc:
                    continue
                links += 1
                target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(f'{path.relative_to(root)}:{number}: link outside repository')
                    continue
                if not target.exists():
                    errors.append(f'{path.relative_to(root)}:{number}: missing {href}')
                elif parsed.fragment and target.suffix == '.md':
                    if unquote(parsed.fragment) not in anchors(target.read_text(encoding='utf-8-sig')):
                        errors.append(f'{path.relative_to(root)}:{number}: missing anchor {href}')
    if errors:
        raise ValueError('\n'.join(errors))
    print(f'Documentation: PASS ({len(files)} Markdown files, {links} local links/anchors, {diagrams} Mermaid blocks; rendering is a separate check)')


if __name__ == '__main__':
    validate()
