"""The Mythril function signature database."""

import functools
import logging
import multiprocessing
import os
import sqlite3
from collections import defaultdict
from typing import List, DefaultDict, Dict

from mythril.ethereum.util import get_solc_json

log = logging.getLogger(__name__)

lock = multiprocessing.Lock()


def synchronized(sync_lock):
    """A decorator synchronizing multi-process access to a resource."""

    def wrapper(f):
        """The decorator's core function.

        :param f:
        :return:
        """

        @functools.wraps(f)
        def inner_wrapper(*args, **kw):
            """

            :param args:
            :param kw:
            :return:
            """
            with sync_lock:
                return f(*args, **kw)

        return inner_wrapper

    return wrapper


class Singleton(type):
    """A metaclass type implementing the singleton pattern."""

    _instances: Dict["Singleton", "Singleton"] = dict()

    @synchronized(lock)
    def __call__(cls, *args, **kwargs):
        """Delegate the call to an existing resource or a new one.

        This is not thread- or process-safe by default. It must be protected with
        a lock.

        :param args:
        :param kwargs:
        :return:
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)

        return cls._instances[cls]


class SQLiteDB(object):
    """Simple context manager for sqlite3 databases.

    Commits everything at exit.
    """

    def __init__(self, path):
        """

        :param path:
        """
        self.path = path
        self.conn = None
        self.cursor = None

    def __enter__(self):
        """

        :return:
        """
        try:
            self.conn = sqlite3.connect(self.path)
        except sqlite3.OperationalError:
            raise sqlite3.OperationalError(f"Unable to Connect to path {self.path}")
        self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, exc_class, exc, traceback):
        """

        :param exc_class:
        :param exc:
        :param traceback:
        """
        self.conn.commit()
        self.conn.close()

    def __repr__(self):
        return "<SQLiteDB path={}>".format(self.path)


class SignatureDB(object, metaclass=Singleton):
    """"""

    def __init__(self, path: str = None) -> None:
        """
        :param path:
        """

        # if we're analysing a Solidity file, store its hashes
        # here to prevent unnecessary lookups
        self.solidity_sigs: DefaultDict[str, List[str]] = defaultdict(list)
        if path is None:
            self.path = os.environ.get("MYTHRIL_DIR") or os.path.join(
                os.path.expanduser("~"), ".mythril"
            )
        self.path = os.path.join(self.path, "signatures.db")

        log.info("Using signature database at %s", self.path)
        # NOTE: Creates a new DB file if it doesn't exist already
        with SQLiteDB(self.path) as cur:
            cur.execute(
                (
                    "CREATE TABLE IF NOT EXISTS signatures"
                    "(byte_sig VARCHAR(10), text_sig VARCHAR(255),"
                    "PRIMARY KEY (byte_sig, text_sig))"
                )
            )

    def __getitem__(self, item: str) -> List[str]:
        """Provide dict interface db[sighash]

        :param item: 4-byte signature string
        :return: list of matching text signature strings
        """
        return self.get(byte_sig=item)

    @staticmethod
    def _normalize_byte_sig(byte_sig: str) -> str:
        """Adds a leading 0x to the byte signature if it's not already there.

        :param byte_sig: 4-byte signature string
        :return: normalized byte signature string
        """
        if not byte_sig.startswith("0x"):
            byte_sig = "0x" + byte_sig
        if not len(byte_sig) == 10:
            raise ValueError(
                "Invalid byte signature %s, must have 10 characters", byte_sig
            )
        return byte_sig

    def add(self, byte_sig: str, text_sig: str) -> None:
        """
        Adds a new byte - text signature pair to the database.
        :param byte_sig: 4-byte signature string
        :param text_sig: resolved text signature
        :return:
        """
        byte_sig = self._normalize_byte_sig(byte_sig)
        with SQLiteDB(self.path) as cur:
            # ignore new row if it's already in the DB (and would cause a unique constraint error)
            cur.execute(
                "INSERT OR IGNORE INTO signatures (byte_sig, text_sig) VALUES (?,?)",
                (byte_sig, text_sig),
            )

    def get(self, byte_sig: str, online_timeout: int = 2) -> List[str]:
        """Get a function text signature for a byte signature 1) try local
        cache 2) try online lookup (if enabled; if not flagged as unavailable)

        :param byte_sig: function signature hash as hexstr
        :param online_timeout: online lookup timeout
        :return: list of matching function text signatures
        """

        byte_sig = self._normalize_byte_sig(byte_sig)

        # check if we have any Solidity signatures to look up
        text_sigs = self.solidity_sigs.get(byte_sig)
        if text_sigs is not None:
            return text_sigs

        # try lookup in the local DB
        with SQLiteDB(self.path) as cur:
            cur.execute("SELECT text_sig FROM signatures WHERE byte_sig=?", (byte_sig,))
            text_sigs = cur.fetchall()

        if text_sigs:
            return [t[0] for t in text_sigs]

        return []

    def import_solidity_file(
        self, file_path: str, solc_binary: str = "solc", solc_settings_json: str = None
    ):
        """Import Function Signatures from solidity source files.

        :param solc_binary:
        :param solc_settings_json:
        :param file_path: solidity source code file path
        :return:
        """
        solc_json = get_solc_json(file_path, solc_binary, solc_settings_json)
        self.add_sigs(file_path, solc_json)

    def add_sigs(self, file_path: str, solc_json):
        for contract in solc_json["contracts"][file_path].values():
            if "methodIdentifiers" not in contract["evm"]:
                continue
            for name, hash_ in contract["evm"]["methodIdentifiers"].items():
                sig = "0x{}".format(hash_)
                if sig in self.solidity_sigs:
                    self.solidity_sigs[sig].append(name)
                else:
                    self.solidity_sigs[sig] = [name]
                self.add(sig, name)

    def __repr__(self):
        return "<SignatureDB path='{}'>".format(self.path)
