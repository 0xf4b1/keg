import os

import requests

from . import blizini, blte
from .archive import ArchiveIndex
from .configfile import BuildConfig, CDNConfig, PatchConfig


def partition_hash(hash: str) -> str:
	return f"{hash[0:2]}/{hash[2:4]}/{hash}"


class BaseCDN:
	def get_item(self, path: str):
		raise NotImplementedError()

	def download_build_config(self, hash: str) -> BuildConfig:
		return BuildConfig(self.download_config(hash))

	def download_cdn_config(self, hash: str) -> CDNConfig:
		return CDNConfig(self.download_config(hash))

	def download_patch_config(self, hash: str) -> PatchConfig:
		return PatchConfig(self.download_config(hash))

	def download_config(self, hash: str) -> dict:
		with self.get_item(f"/config/{partition_hash(hash)}") as resp:
			return blizini.load(resp.read().decode())

	def download_data_index(self, hash: str, verify: bool=False) -> ArchiveIndex:
		with self.get_item(f"/data/{partition_hash(hash)}.index") as resp:
			return ArchiveIndex(resp.read(), hash, verify=verify)

	def download_data(self, hash: str, verify: bool=False) -> bytes:
		with self.get_item(f"/data/{partition_hash(hash)}") as resp:
			data = blte.BLTEDecoder(resp, hash, verify=verify)
			return b"".join(data.blocks)


class RemoteCDN(BaseCDN):
	def __init__(self, cdn):
		assert cdn.all_servers
		self.server = cdn.all_servers[0]
		self.path = cdn.path

	def get_item(self, path: str):
		url = f"{self.server}/{self.path}{path}"
		return requests.get(url, stream=True).raw


class LocalCDN(BaseCDN):
	def __init__(self, base_dir: str) -> None:
		self.base_dir = base_dir

	def get_full_path(self, path: str) -> str:
		return os.path.join(self.base_dir, path.lstrip("/"))

	def get_item(self, path: str):
		return open(self.get_full_path(path), "rb")

	def exists(self, path: str) -> bool:
		return os.path.exists(self.get_full_path(path))


class CacheableCDNWrapper(BaseCDN):
	def __init__(self, cdns_response, base_dir: str) -> None:
		if not os.path.exists(base_dir):
			os.makedirs(base_dir)
		self.local_cdn = LocalCDN(base_dir)
		self.remote_cdn = RemoteCDN(cdns_response)

	def get_item(self, path: str):
		if self.local_cdn.exists(path):
			return self.local_cdn.get_item(path)

		cache_file_path = self.local_cdn.get_full_path(path)
		return HTTPCacheWrapper(self.remote_cdn.get_item(path), cache_file_path)


class HTTPCacheWrapper:
	def __init__(self, obj, path: str) -> None:
		self._obj = obj

		dir_path = os.path.dirname(path)
		if not os.path.exists(dir_path):
			os.makedirs(dir_path)

		self._real_path = path
		self._temp_path = path + ".keg_temp"
		self._cache_file = open(self._temp_path, "wb")

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()
		return False

	def close(self):
		self.read()
		self._cache_file.close()

		# Atomic write&move; make sure there's no partially-written caches.
		os.rename(self._temp_path, self._real_path)

		return self._obj.close()

	def read(self, bytes: int=-1) -> bytes:
		if bytes == -1:
			ret = self._obj.read()
		else:
			ret = self._obj.read(bytes)
		if ret:
			self._cache_file.write(ret)
		return ret