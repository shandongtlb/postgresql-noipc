"""Official upstream versions plus a monotonically increasing local revision."""
import re

def package_versions(manifest):
    revision = manifest['noipc_revision']
    if type(revision) is not int or revision < 1:
        raise ValueError('noipc_revision must be a positive integer')
    source = manifest['debian_version'] + f'+noipc{revision}'
    if manifest['noipc_version'] != source:
        raise ValueError('noipc_version must contain the current +noipcN revision')
    official_binary = manifest.get('binary_version', manifest['debian_version'])
    suffix = official_binary.removeprefix(manifest['debian_version'])
    if suffix and not re.fullmatch(r'\+b[0-9]+', suffix):
        raise ValueError('Unsupported official binary-only revision')
    return {'source': source, 'binary': source + suffix,
            'meta': manifest['metapackage_version'] + f'+noipc{revision}'}
