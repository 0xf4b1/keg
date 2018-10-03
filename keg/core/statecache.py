import os

from .. import psv
from ..remote.http import StatefulResponse
from ..utils import atomic_write, ensure_dir_exists, partition_hash


class StateCache:
	def __init__(self, cache_dir: str) -> None:
		self.cache_dir = cache_dir

	def exists(self, name: str, key: str) -> bool:
		return os.path.exists(self.get_full_path(name, key))

	def get_full_path(self, name: str, key: str) -> str:
		return os.path.join(self.cache_dir, name, partition_hash(key))

	def read(self, name: str, key: str) -> str:
		with open(self.get_full_path(name, key), "r") as f:
			return f.read()

	def read_psv(self, name: str, key: str) -> psv.PSVFile:
		data = self.read(name, key)
		return psv.loads(data)

	def write(self, name: str, key: str, content: bytes) -> int:
		path = self.get_full_path(name, key)
		ensure_dir_exists(path)
		return atomic_write(path, content)

	def write_response(self, response: StatefulResponse) -> int:
		if self.exists(response.name, response.digest):
			return 0
		return self.write(response.name, response.digest, response.content)
