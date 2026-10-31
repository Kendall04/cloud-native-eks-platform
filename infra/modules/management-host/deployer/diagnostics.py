"""Bounded diagnostics: never persist stderr, URLs, messages or command arguments."""
import re
import ssl
import subprocess
import urllib.error

AWS_CODES = {
    'AccessDenied': 'Authorization', 'AccessDeniedException': 'Authorization',
    'UnauthorizedOperation': 'Authorization', 'ExpiredToken': 'Authentication',
    'Throttling': 'Throttling', 'ThrottlingException': 'Throttling',
    'TooManyRequestsException': 'Throttling', 'RequestTimeout': 'Timeout',
    'ServiceUnavailable': 'DependencyUnavailable', 'InternalFailure': 'DependencyUnavailable',
    'NoSuchKey': 'InvalidData', 'NoSuchVersion': 'InvalidData',
}

class CommandFailure(Exception):
    def __init__(self, command, returncode, stderr):
        super().__init__('Fixed command failed')
        self.command = command if command in ('aws', 'helm', 'kubectl') else 'unknown'
        self.returncode = returncode
        # AWS CLI has no structured error output. Extract only an allowlisted code
        # from its fixed envelope; never retain the untrusted remainder.
        match = re.search(r'An error occurred \(([A-Za-z]+)\) when calling', stderr) if command == 'aws' else None
        self.aws_code = match[1] if match and match[1] in AWS_CODES else None


def diagnostic(error):
    if isinstance(error, CommandFailure):
        result = {'errorCategory': AWS_CODES.get(error.aws_code, 'CommandFailure'),
                  'exceptionType': 'CommandFailure', 'command': error.command, 'exitCode': error.returncode}
        if error.aws_code: result['awsErrorCode'] = error.aws_code
        return result
    if isinstance(error, urllib.error.HTTPError):
        status = error.code
        return {'errorCategory': 'Authorization' if status in (401,403) else 'Throttling' if status == 429 else 'DependencyUnavailable' if status >= 500 else 'InvalidData',
                'exceptionType': 'HTTPError', 'httpStatusCode': status}
    if isinstance(error, urllib.error.URLError): return diagnostic(error.reason)
    for kind, category in ((subprocess.TimeoutExpired,'Timeout'), (TimeoutError,'Timeout'),
                           (ssl.SSLError,'TLS'), (OSError,'Network'), (ValueError,'InvalidData')):
        if isinstance(error, kind): return {'errorCategory': category, 'exceptionType': kind.__name__}
    return {'errorCategory':'Unknown', 'exceptionType':'Exception'}
