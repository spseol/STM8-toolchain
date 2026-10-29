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
INCLUDE = ["package.json", "extension.js", "README.md", "src", "media"]

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types>
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
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
    <Categories>Debuggers</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value={engine}/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def files(src):
    for item in INCLUDE:
        path = src / item
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from sorted(p for p in path.rglob("*") if p.is_file())


def pack(src_dir, out_path):
    src = Path(src_dir)
    package = json.loads((src / "package.json").read_text())
    escape = lambda text: text.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    manifest = MANIFEST.format(
        name=quoteattr(package["name"]), version=quoteattr(package["version"]),
        publisher=quoteattr(package["publisher"]), engine=quoteattr(package["engines"]["vscode"]),
        display=escape(package["displayName"]), description=escape(package["description"]),
    )
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("extension.vsixmanifest", manifest)
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        for path in files(src):
            archive.write(path, "extension/" + path.relative_to(src).as_posix())


if __name__ == "__main__":
    pack(HERE, sys.argv[1] if len(sys.argv) > 1 else HERE / "stm8-toolchain.vsix")
