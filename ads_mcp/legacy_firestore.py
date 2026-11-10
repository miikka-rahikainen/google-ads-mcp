"""Firestore addressing compatible with py-key-value-aio 0.4.6 FileTree.

The deployed app explicitly supplied FileTreeStore without sanitizers. Logical
keys therefore address normalized POSIX paths. We hash that *physical* identity
for Firestore and persist it separately for lossless rollback. A migrated file
name is never passed through the logical-key API or Firestore's own sanitizer.
"""

import hashlib
import posixpath
from datetime import datetime, timezone

from key_value.aio._utils.sanitization import SanitizationStrategy
from key_value.aio.stores.firestore import FirestoreStore

INDEX_COLLECTION = "migration_filetree_collections"
LEGACY_ROOT = "/data/oauth"


def physical_path(value: str, *, key: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("Invalid legacy address")
    path = posixpath.normpath(value + (".json" if key else ""))
    if path.startswith("/") or path in {".", ".."} or path.startswith("../"):
        raise ValueError("Legacy path escapes its root")
    if any(len(part.encode("utf-8")) > 255 for part in path.split("/")):
        raise ValueError("Legacy filename exceeds Linux filesystem limits")
    if not key and len((path + "-info.json").encode("utf-8")) > 255:
        raise ValueError("Legacy collection metadata filename is too long")
    if len((LEGACY_ROOT + "/" + path).encode("utf-8")) >= 4096:
        raise ValueError("Legacy path exceeds Linux filesystem limits")
    if not key and "/" in path:
        raise ValueError("Nested legacy collections require separate review")
    return path[:-5] if key else path


def physical_id(path: str) -> str:
    return "ft_" + hashlib.sha256(path.encode("utf-8")).hexdigest()


class LegacyAddress(SanitizationStrategy):
    def __init__(self, *, key: bool):
        self.key = key

    def sanitize(self, value: str) -> str:
        return physical_id(physical_path(value, key=self.key))

    def validate(self, value: str) -> None:
        physical_path(value, key=self.key)


class LegacyFileTreeFirestoreStore(FirestoreStore):
    """Keeps the deployed passthrough FileTree identity and absolute TTL."""

    def __init__(self, **kwargs):
        super().__init__(
            **kwargs,
            key_sanitization_strategy=LegacyAddress(key=True),
            collection_sanitization_strategy=LegacyAddress(key=False),
        )

    async def _setup_collection(self, *, collection: str) -> None:
        from google.api_core.exceptions import AlreadyExists

        physical = physical_path(collection)
        metadata = {
            "version": 1,
            "collection": collection,
            "directory": f"{LEGACY_ROOT}/{physical}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        ref = self._client.collection(INDEX_COLLECTION).document(
            physical_id(physical)
        )
        try:
            await ref.create(metadata)
        except AlreadyExists:
            existing = (await ref.get()).to_dict()
            if not existing or existing.get("collection") != collection:
                raise ValueError(
                    "Legacy collection identity conflict"
                ) from None

    async def _put_managed_entry(
        self, *, key, managed_entry, collection=None
    ) -> None:
        collection = collection or self.default_collection
        item = self._serialization_adapter.dump_dict(entry=managed_entry)
        # Record the physical identity so new writes can be exported too.
        item["_legacy_key"] = physical_path(key, key=True)
        full_path = (
            f"{LEGACY_ROOT}/{physical_path(collection)}/"
            f"{item['_legacy_key']}.json"
        )
        if len(full_path.encode("utf-8")) >= 4096:
            raise ValueError("Legacy path cannot be restored on Linux")
        await self._client.collection(
            physical_id(physical_path(collection))
        ).document(physical_id(item["_legacy_key"])).set(item)

    async def _put_managed_entries(
        self, *, collection, keys, managed_entries, **kwargs
    ) -> None:
        # OAuth writes are small. Preserve per-record absolute expiry supplied
        # by BaseStore rather than recomputing TTL during migration/rollback.
        for key, entry in zip(keys, managed_entries, strict=True):
            await self._put_managed_entry(
                key=key, collection=collection, managed_entry=entry
            )
