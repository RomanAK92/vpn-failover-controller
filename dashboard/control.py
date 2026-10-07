"""Bounded Linux IPC client. No shell, Docker socket or caller supplied paths."""
import json
import os
import pathlib
import socket
import stat
import struct

MAX_REQUEST = 65536 + 8192
MAX_RESPONSE = 32768


class ControlError(ValueError):
    pass


class Control:
    def __init__(self, directory):
        self.directory = pathlib.Path(directory)
        if not self.directory.is_absolute() or not hasattr(socket, 'SO_PEERCRED'):
            raise ControlError('Private control requires a dedicated Linux socket directory.')

    def request(self, action, **fields):
        directory = self.directory
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            raise ControlError('Unsafe private control directory.')
        attributes = directory.stat()
        if (not stat.S_ISDIR(attributes.st_mode) or attributes.st_uid != 0
            or attributes.st_gid != 65532 or attributes.st_mode & 0o777 != 0o750):
            raise ControlError('Private control directory ownership is invalid.')
        path = directory/'prepare.sock'
        attributes = path.lstat()
        if (not stat.S_ISSOCK(attributes.st_mode) or attributes.st_uid != 0
            or attributes.st_gid != 65532 or attributes.st_mode & 0o777 != 0o660):
            raise ControlError('Private control socket ownership is invalid.')
        data = json.dumps({'action': action, **fields}, separators=(',', ':')).encode('utf8')
        if not 1 <= len(data) <= MAX_REQUEST:
            raise ControlError('Private command exceeds its bound.')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(20)
            connection.connect(str(path))
            _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != 0:
                raise ControlError('Private engine identity is invalid.')
            connection.sendall(struct.pack('!I', len(data))+data)
            def exact(size):
                result = bytearray()
                while len(result) < size:
                    chunk = connection.recv(size-len(result))
                    if not chunk: raise ControlError('Private engine response was interrupted.')
                    result.extend(chunk)
                return bytes(result)
            size = struct.unpack('!I', exact(4))[0]
            if not 1 <= size <= MAX_RESPONSE:
                raise ControlError('Private engine response exceeds its bound.')
            response = json.loads(exact(size).decode('utf8'))
        if not isinstance(response, dict) or response.get('ok') is not True or not isinstance(response.get('result'), dict):
            raise ControlError('The engine rejected the operation. Inspect its status before retrying.')
        return response['result']
