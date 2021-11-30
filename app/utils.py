import hashlib
import datetime

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from asyncua.server.user_managers import UserManager
from asyncua.server.users import User, UserRole

from typing import Callable, Dict, List

__all__ = ["lazyeval", "PasswordUserManager", "generate_and_write_certificates"]


class LazyEval:
    _callable: Callable[[], str]

    def __init__(self, func: Callable[[], str]):
        self._callable = func

    def __str__(self) -> str:
        return self._callable()


lazyeval = LazyEval


class PasswordUserManager(UserManager):
    _users: List[Dict[str, str]]

    def __init__(self, users: List[Dict[str, str]]):
        self._users = users

    def get_user(self, iserver, username: str = None, password: str = None, certificate=None):
        for user in self._users:
            if user["username"] == username and user["password"] == hashlib.sha256(password.encode("utf8")).hexdigest():
                return User(role=UserRole.User, name=username)

        return None


def generate_and_write_certificates(hostname: str, cert_path: str, privatekey_path: str):
    one_day = datetime.timedelta(1, 0, 0)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend())
    public_key = private_key.public_key()

    builder = x509.CertificateBuilder()
    builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
    builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)]))
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + (one_day * 365 * 5))
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(hostname),
            x509.DNSName('*.%s' % hostname),
            x509.DNSName('localhost'),
            x509.DNSName('*.localhost'),
        ]),
        critical=False)
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=default_backend())

    with open(cert_path, "x") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM).decode("utf8"))

    with open(privatekey_path, "x") as f:
        f.write(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            ).decode("utf8")
        )
