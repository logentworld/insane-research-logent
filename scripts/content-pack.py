#!/usr/bin/env python3
"""OpenSSL과 Python 표준 라이브러리로 서명 콘텐츠 pack을 만들어요."""

import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


MAX_FILES = 4096
MAX_MANIFEST = 1024 * 1024
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ZIP = 512 * 1024 * 1024
CHUNK = 1024 * 1024
PLUGIN_PATTERN = re.compile(r"[a-z][a-z0-9.-]{0,127}\Z", re.ASCII)
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z", re.ASCII)
SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9._-]+\Z", re.ASCII)
FORBIDDEN_SUFFIXES = {".dex", ".apk", ".jar", ".class", ".aar", ".aab"}
# id-ecPublicKey, prime256v1, 비압축 공개점으로 이루어진 DER SPKI 접두사예요.
P256_SPKI_PREFIX = bytes.fromhex(
    "3059301306072a8648ce3d020106082a8648ce3d03010703420004"
)
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


class PackError(Exception):
    pass


def openssl(*arguments, data=None, pass_fds=()):
    result = subprocess.run(
        ["openssl", *arguments], input=data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, pass_fds=pass_fds, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PackError(f"OpenSSL 실행에 실패했어요: {detail}")
    return result.stdout


def fingerprint(metadata):
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_ctime_ns,
    )


def private_path(value):
    path = Path(value).expanduser().resolve()
    # worktree와 submodule의 .git 파일도 checkout 표시로 취급해요.
    for parent in (path.parent, *path.parent.parents):
        if os.path.lexists(parent / ".git"):
            raise PackError(f"개인키를 Git checkout 안에 둘 수 없어요: {path}")
    return path


def public_der(private_bytes):
    openssl("ec", "-check", "-noout", data=private_bytes)
    public = openssl(
        "ec", "-pubout", "-outform", "DER", "-conv_form", "uncompressed",
        "-param_enc", "named_curve", data=private_bytes,
    )
    if len(public) != 91 or not public.startswith(P256_SPKI_PREFIX):
        raise PackError("개인키는 ECDSA P-256 곡선을 사용해야 해요.")
    return public


@contextlib.contextmanager
def atomic_output(destination):
    destination = Path(destination).expanduser().absolute()
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w+b") as stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def keygen(arguments):
    key = private_path(arguments.key)
    public = Path(arguments.public_key).expanduser().absolute()
    if public.resolve() == key:
        raise PackError("개인키와 공개키의 출력 경로는 달라야 해요.")
    if os.path.lexists(key) or os.path.lexists(Path(arguments.key).expanduser()):
        raise PackError(f"기존 개인키를 덮어쓰지 않아요: {key}")
    private = openssl(
        "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
        "-pkeyopt", "ec_param_enc:named_curve",
    )
    public_bytes = public_der(private)
    # 생성 중 부모 symlink가 바뀌어도 checkout 위치를 다시 확인해요.
    if private_path(arguments.key) != key:
        raise PackError("개인키 출력 경로가 생성 중 바뀌었어요.")
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(private)
            stream.flush()
            os.fsync(stream.fileno())
        with atomic_output(public) as stream:
            stream.write(public_bytes)
    except BaseException:
        try:
            current = key.lstat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                key.unlink()
        except FileNotFoundError:
            pass
        raise
    print(f"개인키를 권한 600으로 만들었어요: {key}")
    print(f"DER SPKI 공개키를 만들었어요: {public}")
    print(f"공개키 SHA256: {hashlib.sha256(public_bytes).hexdigest()}")


@contextlib.contextmanager
def open_directory(root_fd, parts, directories):
    fd = os.dup(root_fd)
    try:
        if fingerprint(os.fstat(fd)) != directories[()]:
            raise PackError("소스 루트가 읽는 중 바뀌었어요.")
        for index, part in enumerate(parts):
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            if fingerprint(os.fstat(fd)) != directories[parts[:index + 1]]:
                raise PackError(f"소스 디렉터리가 읽는 중 바뀌었어요: {'/'.join(parts)}")
        yield fd
    finally:
        os.close(fd)


def collect_source(root_fd):
    directories = {(): fingerprint(os.fstat(root_fd))}
    files = {}
    pending = [()]
    total = 0
    while pending:
        parts = pending.pop()
        with open_directory(root_fd, parts, directories) as fd:
            with os.scandir(fd) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
            for entry in children:
                if entry.name in (".", "..") or not SEGMENT_PATTERN.fullmatch(entry.name):
                    raise PackError(f"허용하지 않는 소스 경로예요: {'/'.join((*parts, entry.name))}")
                child_parts = (*parts, entry.name)
                relative = "/".join(child_parts)
                metadata = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    directories[child_parts] = fingerprint(metadata)
                    pending.append(child_parts)
                elif stat.S_ISREG(metadata.st_mode):
                    if Path(entry.name).suffix.lower() in FORBIDDEN_SUFFIXES:
                        raise PackError(f"실행 코드 컨테이너는 pack에 넣을 수 없어요: {relative}")
                    if metadata.st_size > MAX_FILE:
                        raise PackError(f"파일 크기는 256MiB 이하여야 해요: {relative}")
                    files[relative] = fingerprint(metadata)
                    total += metadata.st_size
                    if len(files) > MAX_FILES or total > MAX_TOTAL:
                        raise PackError("파일은 최대 4096개, 전체 크기는 512MiB 이하여야 해요.")
                else:
                    raise PackError(f"symlink와 일반 파일이 아닌 항목은 넣을 수 없어요: {relative}")
            if fingerprint(os.fstat(fd)) != directories[parts]:
                raise PackError(f"소스 디렉터리가 읽는 중 바뀌었어요: {'/'.join(parts)}")
    if not files:
        raise PackError("소스에 파일이 최소 1개 있어야 해요.")
    return files, directories


def read_source(root_fd, relative, expected, directories, destination=None):
    parts = tuple(relative.split("/"))
    digest = hashlib.sha256()
    size = 0
    with open_directory(root_fd, parts[:-1], directories) as directory:
        fd = os.open(parts[-1], FILE_FLAGS, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            if fingerprint(os.fstat(stream.fileno())) != expected:
                raise PackError(f"소스 파일이 읽기 전에 바뀌었어요: {relative}")
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                if size == 0 and chunk.startswith((b"dex\n", b"cdex")):
                    raise PackError(f"DEX 파일은 pack에 넣을 수 없어요: {relative}")
                size += len(chunk)
                if size > MAX_FILE or size > expected[3]:
                    raise PackError(f"소스 파일 크기가 읽는 중 바뀌었어요: {relative}")
                digest.update(chunk)
                if destination is not None:
                    destination.write(chunk)
            if size != expected[3] or fingerprint(os.fstat(stream.fileno())) != expected:
                raise PackError(f"소스 파일이 읽는 중 바뀌었어요: {relative}")
    return digest.hexdigest(), size


def zip_info(name):
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.create_system = 3
    entry.external_attr = (stat.S_IFREG | 0o644) << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    return entry


def sign(arguments):
    if not PLUGIN_PATTERN.fullmatch(arguments.plugin) or any(
        not segment for segment in arguments.plugin.split(".")
    ):
        raise PackError("plugin은 [a-z][a-z0-9.-]{0,127} 형식이며 점 사이에 빈 구간이 없어야 해요.")
    if not VERSION_PATTERN.fullmatch(arguments.version):
        raise PackError("version은 영숫자로 시작하는 1~96자의 영숫자·점·밑줄·하이픈이어야 해요.")
    if arguments.api_min <= 0 or arguments.api_max < arguments.api_min:
        raise PackError("API 범위는 양의 정수이며 api-min이 api-max 이하여야 해요.")
    key = private_path(arguments.key)
    output = Path(arguments.output).expanduser().absolute()
    if output.resolve() == key:
        raise PackError("pack 출력으로 개인키를 덮어쓸 수 없어요.")
    key_fd = os.open(key, FILE_FLAGS)
    with os.fdopen(key_fd, "rb") as key_stream:
        if not stat.S_ISREG(os.fstat(key_fd).st_mode):
            raise PackError("개인키는 일반 파일이어야 해요.")
        os.fchmod(key_fd, 0o600)
        key_metadata = fingerprint(os.fstat(key_fd))
        private = key_stream.read()
        public = public_der(private)
        if arguments.public_key is not None:
            if Path(arguments.public_key).expanduser().read_bytes() != public:
                raise PackError("지정한 DER SPKI 공개키가 개인키와 일치하지 않아요.")
        if fingerprint(os.fstat(key_fd)) != key_metadata or private_path(arguments.key) != key:
            raise PackError("개인키가 읽는 중 바뀌었어요.")
        root_fd = os.open(Path(arguments.source).expanduser(), DIRECTORY_FLAGS)
        staged = None
        try:
            # 이름 없는 ZIP을 먼저 열어서 소스의 최초 snapshot 이후에는 디렉터리를 건드리지 않아요.
            staged = tempfile.TemporaryFile(dir=output.parent)
            files, directories = collect_source(root_fd)
            prefix = f"assets/plugins/{arguments.plugin.rsplit('.', 1)[-1]}/"
            lines = [
                "logent-content-v1\n", f"plugin={arguments.plugin}\n",
                f"version={arguments.version}\n", f"apiMin={arguments.api_min}\n",
                f"apiMax={arguments.api_max}\n",
            ]
            hashes = {}
            for relative in sorted(files):
                if len(prefix + relative) > 1024:
                    raise PackError(f"ZIP 경로는 1024자 이하여야 해요: {relative}")
                digest, size = read_source(root_fd, relative, files[relative], directories)
                hashes[relative] = (digest, size)
                lines.append(f"{digest}\t{size}\t{prefix}{relative}\n")
            manifest = "".join(lines).encode("ascii")
            if len(manifest) > MAX_MANIFEST:
                raise PackError("manifest.txt는 1MiB 이하여야 해요.")
            key_stream.seek(0)
            signature = openssl(
                "dgst", "-sha256", "-sign", f"/dev/fd/{key_fd}",
                data=manifest, pass_fds=(key_fd,),
            )
            if len(signature) > 256:
                raise PackError("DER 서명은 256바이트 이하여야 해요.")
            if fingerprint(os.fstat(key_fd)) != key_metadata:
                raise PackError("개인키가 서명 중 바뀌었어요.")
            total = sum(size for _, size in hashes.values()) + len(manifest) + len(signature)
            if total > MAX_TOTAL:
                raise PackError("manifest와 서명을 포함한 전체 크기는 512MiB 이하여야 해요.")
            # 완료된 ZIP 바이트만 출력 경로에 원자적으로 배포해요.
            with staged:
                with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(zip_info("manifest.txt"), manifest)
                    archive.writestr(zip_info("manifest.sig"), signature)
                    for relative in sorted(files):
                        with archive.open(zip_info(prefix + relative), "w") as destination:
                            actual = read_source(
                                root_fd, relative, files[relative], directories, destination,
                            )
                        if actual != hashes[relative]:
                            raise PackError(f"원본과 ZIP의 SHA256 또는 크기가 달라요: {relative}")
                if staged.tell() > MAX_ZIP:
                    raise PackError("압축 ZIP 크기는 512MiB 이하여야 해요.")
                final_files, final_directories = collect_source(root_fd)
                if final_files != files or final_directories != directories:
                    raise PackError("소스가 pack 생성 중 바뀌었어요.")
                staged.seek(0)
                with atomic_output(output) as destination:
                    shutil.copyfileobj(staged, destination, CHUNK)
        finally:
            if staged is not None:
                staged.close()
            os.close(root_fd)
    print(f"서명 콘텐츠 pack을 만들었어요: {output}")
    print(f"공개키 SHA256: {hashlib.sha256(public).hexdigest()}")


def parser():
    result = argparse.ArgumentParser(description="서명 콘텐츠 pack과 ECDSA P-256 키를 만들어요.")
    commands = result.add_subparsers(dest="command", required=True, help="실행할 작업을 골라 주세요.")
    generate = commands.add_parser("keygen", help="Git checkout 밖에 개인키와 DER 공개키를 만들어요.")
    generate.add_argument("--key", required=True, help="새 PEM 개인키 경로를 지정해 주세요. 기존 파일은 보존해요.")
    generate.add_argument("--public-key", required=True, help="DER SPKI 공개키 출력 경로를 지정해 주세요.")
    generate.set_defaults(action=keygen)
    pack = commands.add_parser("sign", help="플러그인 자산을 검증하고 서명 ZIP으로 만들어요.")
    pack.add_argument("--source", required=True, help="플러그인 assets 내부 루트 디렉터리를 지정해 주세요.")
    pack.add_argument("--plugin", required=True, help="플러그인 ID를 지정해 주세요.")
    pack.add_argument("--version", required=True, help="콘텐츠 버전을 지정해 주세요.")
    pack.add_argument("--api-min", required=True, type=int, help="최소 API 양의 정수를 지정해 주세요.")
    pack.add_argument("--api-max", required=True, type=int, help="최대 API 양의 정수를 지정해 주세요.")
    pack.add_argument("--key", required=True, help="Git checkout 밖의 PEM 개인키를 지정해 주세요.")
    pack.add_argument("--public-key", help="개인키와 일치해야 하는 DER SPKI 공개키를 지정해 주세요.")
    pack.add_argument("--output", required=True, help="완성된 ZIP 출력 경로를 지정해 주세요. 실패하면 기존 파일을 보존해요.")
    pack.set_defaults(action=sign)
    return result


def main():
    arguments = parser().parse_args()
    try:
        arguments.action(arguments)
    except (PackError, OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        print(f"콘텐츠 pack 작업에 실패했어요: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
