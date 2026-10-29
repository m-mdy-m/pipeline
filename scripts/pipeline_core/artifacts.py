"""Local artifact store: safe filenames, atomic copies, SHA-256 and inventory."""
from __future__ import annotations
import hashlib,json,os,shutil,tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from .errors import ArtifactError
@dataclass(frozen=True)
class ArtifactReceipt:
    name:str
    path:str
    size_bytes:int
    sha256:str
    def to_dict(self):return {"name":self.name,"path":self.path,"size_bytes":self.size_bytes,"sha256":self.sha256}
def sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda:file.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()
class LocalArtifactStore:
    def __init__(self,directory:str|Path):self.directory=Path(directory).expanduser().resolve()
    def publish(self,sources:Iterable[str|Path],*,overwrite:bool=False)->list[ArtifactReceipt]:
        paths=[];names=set()
        for item in (Path(s).expanduser() for s in sources):
            if item.is_symlink():raise ArtifactError(f"Artifact symlink rejected: {item}")
            source=item.resolve(strict=True)
            if not source.is_file():raise ArtifactError(f"Artifact must be a regular file: {source}")
            key=source.name.casefold()
            if not source.name or key in names:raise ArtifactError(f"Artifact filename collision: {source.name}")
            names.add(key);paths.append(source)
        if not paths:raise ArtifactError("At least one artifact is required")
        self.directory.mkdir(parents=True,exist_ok=True);staged=[]
        try:
            for source in paths:
                target=self.directory/source.name
                if target.exists() and not overwrite:raise ArtifactError(f"Artifact already exists: {target}")
                with tempfile.NamedTemporaryFile(dir=self.directory,prefix=f".{source.name}.",suffix=".tmp",delete=False) as out:
                    temp=Path(out.name)
                    with source.open("rb") as incoming:shutil.copyfileobj(incoming,out)
                    out.flush();os.fsync(out.fileno())
                staged.append((temp,target))
            for temp,target in staged:
                if target.exists() and not overwrite:raise ArtifactError(f"Artifact appeared during publish: {target}")
                temp.replace(target)
            receipts=[ArtifactReceipt(s.name,str(self.directory/s.name),(self.directory/s.name).stat().st_size,sha256_file(self.directory/s.name)) for s in paths]
            self.write_manifest(receipts);return receipts
        except Exception:
            for temp,_ in staged:
                if temp.exists():temp.unlink()
            raise
    def write_manifest(self,receipts:list[ArtifactReceipt])->Path:
        self.directory.mkdir(parents=True,exist_ok=True);path=self.directory/"artifacts.json"
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",newline="\n",dir=self.directory,prefix=".artifacts.",suffix=".tmp",delete=False) as out:
            temp=Path(out.name);json.dump({"schema_version":1,"artifacts":[x.to_dict() for x in receipts]},out,indent=2,sort_keys=True)
            out.write("\n");out.flush();os.fsync(out.fileno())
        temp.replace(path);return path
