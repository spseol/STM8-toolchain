#!/usr/bin/env python3
"""Pack the extension into a VSIX (a zip) without vsce or Node.js.

Usage: pack.py [OUT.vsix]   (default: stm8-toolchain.vsix next to this file)
"""
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
# what the editor needs; tests, bin/, make helpers and design notes stay out
INCLUDE = ["package.json", "extension.js", "README.md", "CHANGELOG.md", "src", "media"]
# repo root: the licence is shipped as extension/LICENSE.txt
ROOT = HERE.parents[1]
LICENSE = ROOT / "LICENSE"

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types>
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".txt" ContentType="text/plain"/>
  <Default Extension=".png" ContentType="image/png"/>
  <Default Extension=".svg" ContentType="image/svg+xml"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id={name} Version={version} Publisher={publisher}/>
    <DisplayName>{display}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Categories>{categories}</Categories>
{tags}
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value={engine}/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
{links}    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
{assets}  </Assets>
</PackageManifest>
"""


def files(src):
    for item in INCLUDE:
        path = src / item
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob("*") if p.is_file())


# (asset type, path in the VSIX); emitted only when the file is packed
ASSETS = [
    ("Microsoft.VisualStudio.Services.Icons.Default", "extension/media/icon.png"),
    ("Microsoft.VisualStudio.Services.Content.Details", "extension/README.md"),
    ("Microsoft.VisualStudio.Services.Content.Changelog", "extension/CHANGELOG.md"),
    ("Microsoft.VisualStudio.Services.Content.License", "extension/LICENSE.txt"),
]


def extra_files(src):
    """(source file, name in the VSIX) of everything except INCLUDE."""
    if LICENSE.is_file():
        yield LICENSE, "extension/LICENSE.txt"


def package_files(src):
    for path in files(src):
        yield path, "extension/" + path.relative_to(src).as_posix()
    yield from extra_files(src)


def metadata(package, names):
    """The Tags, Properties (links) and Assets of the manifest; each only when its source exists."""
    escape_text = lambda text: text.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    tags = ",".join(package.get("keywords", []))
    repo = package.get("repository")
    repo = repo.get("url") if isinstance(repo, dict) else repo
    repo = repo[:-4] if repo and repo.endswith(".git") else repo
    links = [("Source", repo), ("Getstarted", repo), ("Support", (package.get("bugs") or {}).get("url")),
             ("Learn", package.get("homepage"))]
    return {
        "tags": f"    <Tags>{escape_text(tags)}</Tags>\n" if tags else "",
        "links": "".join(f"      <Property Id=\"Microsoft.VisualStudio.Services.Links.{kind}\" Value={quoteattr(url)}/>\n"
                         for kind, url in links if url),
        "assets": "".join(f"    <Asset Type={quoteattr(kind)} Path={quoteattr(path)} Addressable=\"true\"/>\n"
                          for kind, path in ASSETS if path in names),
    }


def pack(src_dir, out_path):
    src = Path(src_dir)
    package = json.loads((src / "package.json").read_text())
    escape = lambda text: text.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    entries = list(package_files(src))
    names = {name for _, name in entries}
    manifest = MANIFEST.format(
        name=quoteattr(package["name"]), version=quoteattr(package["version"]),
        publisher=quoteattr(package["publisher"]), engine=quoteattr(package["engines"]["vscode"]),
        display=escape(package["displayName"]), description=escape(package["description"]),
        categories=escape(",".join(package.get("categories", []))), **metadata(package, names),
    )
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("extension.vsixmanifest", manifest)
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        for path, name in entries:
            archive.write(path, name)


if __name__ == "__main__":
    pack(HERE, sys.argv[1] if len(sys.argv) > 1 else HERE / "stm8-toolchain.vsix")
