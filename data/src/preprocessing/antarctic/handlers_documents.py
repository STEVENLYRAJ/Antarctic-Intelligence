"""Metadata / documentation files: ISO 19139 XML, saved HTML index pages, PDF, PNG, text, executables.

These are inspected and their metadata extracted, but they are NOT scientific datasets, so their
status is ``metadata_inspected`` (or ``unsupported`` for software), never ``processed``.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .common import add_output, finish, issue, new_record, step, write_json
from .config import PROCESSED_DIR

NS = {"gmd": "http://www.isotc211.org/2005/gmd", "gco": "http://www.isotc211.org/2005/gco",
      "gml": "http://www.opengis.net/gml/3.2", "gmx": "http://www.isotc211.org/2005/gmx"}


def _txt(el):
    return " ".join(el.itertext()).strip() if el is not None else None


def parse_iso_xml(path: Path) -> dict:
    root = ET.parse(path).getroot()
    md = root.find(".//gmd:MD_Metadata", NS)
    md = root if md is None else md
    ident = md.find(".//gmd:identificationInfo", NS)
    out = {
        "file_identifier": _txt(md.find("gmd:fileIdentifier", NS)),
        "title": _txt(ident.find(".//gmd:citation//gmd:title", NS)) if ident is not None else None,
        "abstract": (_txt(ident.find(".//gmd:abstract", NS)) or "")[:2500] if ident is not None else None,
        "temporal_begin": _txt(md.find(".//gml:beginPosition", NS)),
        "temporal_end": _txt(md.find(".//gml:endPosition", NS)) or "ongoing / not specified",
        "bbox": {k: _txt(md.find(f".//gmd:{k}", NS)) for k in ("westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude")},
        "keywords": sorted({_txt(k) for k in md.findall(".//gmd:keyword", NS) if _txt(k)})[:60],
        "use_limitation": _txt(md.find(".//gmd:useLimitation", NS)),
        "other_constraints": _txt(md.find(".//gmd:otherConstraints", NS)),
        "online_resources": sorted({_txt(u) for u in md.findall(".//gmd:linkage/gmd:URL", NS) if _txt(u)}),
        "contacts": sorted({_txt(o) for o in md.findall(".//gmd:organisationName", NS) if _txt(o)}),
    }
    doi = re.search(r"https?://doi\.org/[0-9.]+/[\w.-]+", out["abstract"] or "")
    out["doi"] = doi.group(0) if doi else None
    return out


def process_iso_xml(path: Path, dataset_id: str, product_id: str) -> dict:
    rec = new_record(f"{dataset_id}__iso_metadata", f"ISO 19139 metadata record for {product_id}", [path], "iso_metadata", "Copernicus Marine Service")
    try:
        meta = parse_iso_xml(path)
        meta["product_id"] = product_id
        step(rec, f"Parsed CSW GetRecordById response: '{meta['title']}', {meta['temporal_begin']}..{meta['temporal_end']}, "
                  f"{len(meta['online_resources'])} online resources")
        rec["metrics"] = meta
        out = PROCESSED_DIR / "metadata" / f"{product_id}_iso_metadata.json"
        write_json(meta, out)
        add_output(rec, out, "json", "Extracted ISO metadata fields")
        rec["validation"] = {"xml_well_formed": True, "title_present": bool(meta["title"])}
        return finish(rec, "metadata_inspected")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_html_index(path: Path, dataset_id: str, name: str, provider: str) -> dict:
    rec = new_record(f"{dataset_id}__html", name, [path], "saved_web_page", provider)
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
        title = re.search(r"<title>(.*?)</title>", t, re.S | re.I)
        links = re.findall(r'href="([^"]+)"', t)
        services = re.findall(r'<li><a href="([^"]+)">([^<]+)</a>\s*\((\w+)\)', t)
        rec["metrics"] = {"title": title.group(1).strip() if title else None, "links": links,
                          "services": [{"path": p, "name": n, "type": ty} for p, n, ty in services],
                          "index_entries": re.findall(r'<a href="([^"]+/)">', t)}
        step(rec, f"Parsed saved page '{rec['metrics']['title']}': {len(links)} links, {len(services)} map services")
        issue(rec, "info", "catalog_only", "Saved directory/service listing - describes where data live; contains no scientific values", None)
        rec["validation"] = {"parsed": True}
        return finish(rec, "metadata_inspected")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_pdf(path: Path, dataset_id: str) -> dict:
    rec = new_record(f"{dataset_id}__report_pdf", "NCALM Dry Valleys LiDAR collection report (PDF)", [path], "documentation", "NCALM")
    try:
        b = path.read_bytes()
        pages = len(re.findall(rb"/Type\s*/Page[^s]", b))
        lin = re.search(rb"/Linearized.*?/N (\d+)", b[:2048], re.S)
        rec["metrics"] = {"pdf_version": b[:8].decode(errors="replace"), "page_objects_counted": pages,
                          "linearized_page_count": int(lin.group(1)) if lin else None, "size_bytes": len(b)}
        step(rec, f"PDF header {rec['metrics']['pdf_version']}, page count {rec['metrics']['linearized_page_count'] or pages}")
        issue(rec, "info", "documentation", "Documentation of the LiDAR acquisition; text was not extracted (no PDF text library required)", None)
        rec["validation"] = {"pdf_header_valid": b.startswith(b"%PDF")}
        return finish(rec, "metadata_inspected")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_png(path: Path, dataset_id: str) -> dict:
    from PIL import Image
    rec = new_record(f"{dataset_id}__figure_png", "Copernicus Marine OMI product key figure (PNG)", [path], "product_figure", "Copernicus Marine Service")
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            rec["metrics"] = {"size_px": list(im.size), "mode": im.mode, "dpi": im.info.get("dpi")}
        step(rec, f"PNG verified: {im.size[0]}x{im.size[1]} {rec['metrics']['mode']}")
        issue(rec, "info", "documentation", "Rendered product figure (same image as the official STAC 'omiFigure' asset); not data", None)
        rec["validation"] = {"image_verified": True}
        return finish(rec, "metadata_inspected")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_glims_docs(readme: Path, citations: Path) -> dict:
    rec = new_record("glims_documentation", "GLIMS download package documentation", [readme, citations], "documentation", "GLIMS / NSIDC")
    try:
        c = citations.read_text(encoding="utf-8", errors="replace")
        rec["metrics"] = {
            "readme_lines": len(readme.read_text(encoding="utf-8", errors="replace").splitlines()),
            "citations_bytes": len(c),
            "submission_ids_referenced": len(set(re.findall(r"[Ss]ubmission ID:?\s*(\d+)", c))),
            "doi_count": len(set(re.findall(r"doi\.org/[^\s,;]+|doi:\s*[^\s,;]+", c, re.I))),
            "coordinate_statement": "All data are in the longitude/latitude coordinate system on the WGS-84 datum (CITATIONS.txt)",
            "field_documentation_url": "http://www.glims.org/MapsAndDocs/downloaded_field_desc.html",
        }
        step(rec, f"Read README and CITATIONS ({rec['metrics']['citations_bytes']:,} bytes; {rec['metrics']['doi_count']} DOIs)")
        rec["validation"] = {"readable": True}
        return finish(rec, "metadata_inspected")
    except Exception as e:
        rec["errors"].append(f"{type(e).__name__}: {e}")
        return finish(rec, "failed")


def process_executable(path: Path) -> dict:
    rec = new_record("earthdata_download_installer", "NASA Earthdata Download application installer", [path], "software", "NASA Earthdata")
    rec["domain_relevance"] = "not_data"
    issue(rec, "info", "not_a_dataset", "Windows installer (PE executable) for a download manager; not scientific data. "
          "Not executed; recommend moving it out of DATAS/", None)
    rec["metrics"] = {"size_bytes": path.stat().st_size, "pe_header": path.read_bytes()[:2] == b"MZ"}
    rec["validation"] = {"identified": True}
    step(rec, "Identified as Windows executable; excluded from processing")
    return finish(rec, "unsupported")
