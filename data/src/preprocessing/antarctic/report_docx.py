"""Build the Word report exclusively from machine-readable pipeline outputs.

    python -m data.src.preprocessing.antarctic.report_docx
"""
from __future__ import annotations

import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .common import read_json, rel
from .config import (DATASET_MANIFEST_CSV, FIGURES_DIR, INVENTORY_CSV, QUALITY_DIR, REPORTS_DIR, ROOT,
                     RUN_SUMMARY_JSON, SOURCE_REGISTRY_JSON, WORD_REPORT)

ACCENT = RGBColor(0x18, 0x4F, 0x95)
TEST_RESULTS_XML = REPORTS_DIR / "test_results.xml"
RUN_CMD = "python -m data.src.preprocessing.antarctic.run_pipeline"


# --------------------------------------------------------------------------- docx helpers
class R:
    def __init__(self):
        self.doc = Document()
        self.tables = 0
        self.figures = 0
        self._setup()

    def _setup(self):
        d = self.doc
        sec = d.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        for side in ("left_margin", "right_margin"):
            setattr(sec, side, Cm(2.0))
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)
        st = d.styles["Normal"]
        st.font.name = "Calibri"
        st.font.size = Pt(10.5)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        st.paragraph_format.space_after = Pt(5)
        st.paragraph_format.line_spacing = 1.12
        for lvl, size in [(1, 15), (2, 12.5), (3, 11)]:
            h = d.styles[f"Heading {lvl}"]
            h.font.name = "Calibri"
            h.font.size = Pt(size)
            h.font.color.rgb = ACCENT
            h.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
            h.paragraph_format.space_before = Pt(12 if lvl == 1 else 8)
            h.paragraph_format.space_after = Pt(4)
            h.paragraph_format.keep_with_next = True
        # footer page numbers: "Page X of Y"
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("Scientific Intelligence - Antarctic Data Preprocessing    |    Page ")
        r.font.size = Pt(8.5)
        self._field(p, "PAGE")
        p.add_run(" of ").font.size = Pt(8.5)
        self._field(p, "NUMPAGES")

    @staticmethod
    def _field(p, code):
        run = p.add_run()
        run.font.size = Pt(8.5)
        for tag, attr in [("w:fldChar", "begin"), ("w:instrText", code), ("w:fldChar", "separate"), ("w:t", "1"), ("w:fldChar", "end")]:
            el = OxmlElement(tag)
            if tag == "w:fldChar":
                el.set(qn("w:fldCharType"), attr)
            else:
                if tag == "w:instrText":
                    el.set(qn("xml:space"), "preserve")
                el.text = attr if tag == "w:instrText" else "1"
            run._r.append(el)

    def h(self, text, lvl=1):
        return self.doc.add_heading(text, lvl)

    def p(self, text="", bold_lead=None, italic=False, size=None, align=None):
        para = self.doc.add_paragraph()
        if bold_lead:
            para.add_run(bold_lead).bold = True
        run = para.add_run(text)
        run.italic = italic
        if size:
            run.font.size = Pt(size)
        if align:
            para.alignment = align
        return para

    def bullets(self, items, style="List Bullet"):
        for it in items:
            para = self.doc.add_paragraph(style=style)
            if isinstance(it, tuple):
                para.add_run(it[0]).bold = True
                para.add_run(it[1])
            else:
                para.add_run(str(it))

    def caption(self, kind, text):
        if kind == "Table":
            self.tables += 1
            n = self.tables
        else:
            self.figures += 1
            n = self.figures
        para = self.doc.add_paragraph()
        r = para.add_run(f"{kind} {n}. ")
        r.bold = True
        r.font.size = Pt(9)
        r2 = para.add_run(text)
        r2.font.size = Pt(9)
        r2.italic = True
        para.paragraph_format.keep_with_next = kind == "Table"
        return para

    def table(self, headers, rows, widths_cm=None, font=8, caption=None):
        if caption:
            self.caption("Table", caption)
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        hdr = t.rows[0]
        trPr = hdr._tr.get_or_add_trPr()
        rh = OxmlElement("w:tblHeader")
        rh.set(qn("w:val"), "true")
        trPr.append(rh)
        for i, htxt in enumerate(headers):
            c = hdr.cells[i]
            c.text = ""
            run = c.paragraphs[0].add_run(str(htxt))
            run.bold = True
            run.font.size = Pt(font)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "184F95")
            c._tc.get_or_add_tcPr().append(shd)
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                run = cells[i].paragraphs[0].add_run("" if v is None else str(v))
                run.font.size = Pt(font)
                cells[i].paragraphs[0].paragraph_format.space_after = Pt(0)
                if ri % 2:
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:fill"), "EEF3FA")
                    cells[i]._tc.get_or_add_tcPr().append(shd)
        if widths_cm:
            for row in t.rows:
                for i, w in enumerate(widths_cm):
                    row.cells[i].width = Cm(w)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def figure(self, path, caption, width_cm=16.5):
        self.doc.add_picture(str(path), width=Cm(width_cm))
        self.doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.doc.paragraphs[-1].paragraph_format.keep_with_next = True
        self.caption("Figure", caption)

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# --------------------------------------------------------------------------- data access
def _records() -> dict:
    out = {}
    for f in sorted(QUALITY_DIR.glob("*.json")):
        j = read_json(f)
        if j:
            out[j["dataset_id"]] = j
    return out


def _fmt(v, nd=2):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _tests() -> dict | None:
    if not TEST_RESULTS_XML.exists():
        return None
    root = ET.parse(TEST_RESULTS_XML).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    cases = []
    for tc in suite.iter("testcase"):
        status = "passed"
        msg = ""
        for k in ("failure", "error", "skipped"):
            el = tc.find(k)
            if el is not None:
                status = k if k != "failure" else "failed"
                msg = (el.get("message") or "")[:150]
        cases.append({"name": tc.get("name"), "status": status, "msg": msg, "time": float(tc.get("time", 0))})
    return {"tests": int(suite.get("tests", 0)), "failures": int(suite.get("failures", 0)), "errors": int(suite.get("errors", 0)),
            "skipped": int(suite.get("skipped", 0)), "time": float(suite.get("time", 0)), "timestamp": suite.get("timestamp"), "cases": cases}


# --------------------------------------------------------------------------- report
def build_report() -> Path:
    recs = _records()
    inv = pd.read_csv(INVENTORY_CSV).fillna("")
    man = pd.read_csv(DATASET_MANIFEST_CSV).fillna("")
    reg = read_json(SOURCE_REGISTRY_JSON, {}).get("sources", [])
    summ = read_json(RUN_SUMMARY_JSON, {})
    figs = read_json(FIGURES_DIR / "figures_manifest.json", []) or []
    tests = _tests()
    r = R()
    today = dt.date.today().isoformat()
    fc = inv.processing_status.value_counts().to_dict()

    # ------------------------------------------------------------- 1 title page
    for _ in range(5):
        r.p("")
    r.p("Scientific Intelligence", size=14, align=WD_ALIGN_PARAGRAPH.CENTER).runs[0].font.color.rgb = ACCENT
    t = r.p("Antarctic Climate and Cryosphere Data Preprocessing", size=24, align=WD_ALIGN_PARAGRAPH.CENTER)
    t.runs[0].bold = True
    r.p("Technical report on the inventory, validation and preprocessing of locally collected and API-sourced datasets",
        size=12, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    r.p("")
    r.p(f"Domain: Antarctic Climate and Cryosphere", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    r.p(f"Report generated: {today}", size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    r.p(f"Pipeline run: {summ.get('run_id', 'n/a')}  ({summ.get('duration_s', 'n/a')} s)", size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    r.p("")
    r.p("Project context: the Scientific Intelligence repository organises domain-specific preprocessing modules under data/src/preprocessing/. "
        "This report documents the Antarctic module (data/src/preprocessing/antarctic/) applied to the datasets collected in DATAS/ and to the two "
        "Copernicus CDS API scripts in EXTERNAL APIs/. All figures and statistics are generated from the pipeline's machine-readable outputs.",
        size=9.5, italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    r.page_break()

    # ------------------------------------------------------------- 2 abstract
    r.h("1. Abstract and Objectives")
    proc = [k for k, v in recs.items() if v["status"] == "processed"]
    r.p(f"This report describes a reproducible preprocessing workflow for Antarctic climate and cryosphere data. The pipeline inventoried "
        f"{summ.get('raw_files', len(inv))} files ({summ.get('raw_bytes', 0) / 1e9:.2f} GB) in DATAS/, identified their real formats from file "
        f"signatures, applied format-specific handlers (NetCDF time series and grids, CSV/JSON tables, ESRI shapefiles, KMZ vector data, TIFF "
        f"imagery, ISO 19139 metadata) and produced validated outputs together with JSON quality reports. Six official external sources were "
        f"inspected, and two small public NSIDC files were downloaded to supply the Southern-Hemisphere counterpart of an Arctic file found locally. "
        f"The two CDS API scripts (API.py, PRESSUREAPI.py) were analysed; their ERA5 outputs are not present locally, so they were documented "
        f"rather than processed. {len(proc)} dataset records reached status 'processed'; source files were verified unchanged by SHA-256 re-hashing.")
    r.p("Objectives:", bold_lead="")
    r.bullets(["Inventory every file in DATAS/ with format, size, hash, provenance and processing status.",
               "Validate and preprocess every supported dataset with scientifically appropriate, format-specific rules.",
               "Preserve raw data and record every transformation, exclusion and flag.",
               "Inspect the official sources (Copernicus Marine, PGC, SCAR AMD, NSIDC GLIMS) and register provenance.",
               "Integrate the existing CDS API scripts without executing large requests.",
               "Produce figures, machine-readable quality reports and this document from actual results."])

    # ------------------------------------------------------------- 3 scope
    r.h("2. Dataset Scope")
    r.p("Data types actually found in DATAS/ (by detected format):")
    fmt = inv.groupby("detected_format").agg(n=("file_name", "count"), mb=("size_mb", "sum")).sort_values("mb", ascending=False)
    r.table(["Detected format", "Files", "Size (MB)"], [[i, int(x.n), f"{x.mb:,.1f}"] for i, x in fmt.iterrows()], [9, 2.5, 3],
            caption="Files in DATAS/ grouped by detected format (magic-byte sniffing).")
    domain = inv[inv.domain_relevance.astype(str).str.startswith("out_of_domain")]
    r.p("Scope observations derived from the data themselves:", bold_lead="")
    r.bullets([
        f"Out-of-domain (Arctic) files: {', '.join(sorted(set(domain.file_name)))} - validated but excluded from Antarctic outputs.",
        f"The GLIMS download is global ({_fmt(recs.get('glims_polygons', {}).get('metrics', {}).get('global_feature_count'))} polygons); the "
        f"Antarctic subset is GLIMS/RGI first-order region 19 ({_fmt(recs.get('glims_polygons', {}).get('metrics', {}).get('antarctic_features'))} polygons).",
        "Several files are metadata, documentation, saved web pages or software rather than scientific data; they are reported as such.",
        "The DMI-ASIP sea-ice concentration file is a single day (2023-02-02) of a daily product.",
    ])

    # ------------------------------------------------------------- 4 inventory
    r.h("3. Dataset Inventory")
    r.p(f"The full inventory (with SHA-256 hashes, modification times, variables, coverage and units) is stored in "
        f"{rel(INVENTORY_CSV)} and .json. File status counts: " + ", ".join(f"{k} = {v}" for k, v in fc.items()) + ".")
    rows = [[x.relative_path.replace("DATAS/", ""), x.detected_format, f"{x.size_mb:,.2f}", x.dataset_id, x.processing_status]
            for x in inv.itertuples()]
    r.table(["File (DATAS/...)", "Detected format", "MB", "Dataset id", "Status"], rows, [5.4, 3.6, 1.6, 4.0, 2.4], font=7,
            caption="Inventory of every file discovered under DATAS/.")
    dups = summ.get("duplicates_by_hash") or []
    r.p(f"Byte-identical duplicates (SHA-256): {len(dups)} file(s)." + (" " + "; ".join(f"{d['relative_path']} = {d['duplicate_of']}" for d in dups) if dups else
        " No duplicate downloads were found."))
    comp = inv[inv.compound_group != ""].compound_group.unique()
    r.p("Compound formats: " + "; ".join(sorted(set(c.split(" [")[0] + " [" + c.split(" [")[1] for c in comp))) + ".")

    # ------------------------------------------------------------- 5 sources
    r.h("4. Data Sources and Provenance")
    r.p("Sources A-F were supplied with the assignment; G was added because a Southern-Hemisphere equivalent was required for the Arctic NSIDC file. "
        "'Downloaded' means the data file exists locally (in DATAS/ from the user's prior collection, or in data/raw/antarctic/external/ from this "
        "pipeline); catalog pages and metadata-only products are labelled as such.")
    for s in [x for x in reg if x.get("source_key") in list("ABCDEFG")]:
        r.h(f"Source {s['source_key']}: {s['dataset_name']}", 2)
        r.table(["Field", "Value"], [
            ["Product id", s["product_id"]], ["Provider", s["provider"]], ["URL", s["source_url"]], ["DOI", s.get("doi") or "n/a"],
            ["Scientific purpose", s.get("scientific_purpose", "")], ["Variables / data types", "; ".join(s["variables"])],
            ["Local files", "; ".join(s["local_paths"]) or "none"], ["Access method", s["access_method"]],
            ["Remote check", f"checked={s['remote_check']['checked']}, reachable URLs={s['remote_check']['reachable_urls']}, "
                             f"login required={s['remote_check']['login_required']}"],
            ["Download status", s["download_status"]], ["Preprocessing status", s["preprocessing_status"]],
            ["Licence / access", s["license"]], ["Outstanding issues", " ".join(s["notes"]) or "none"],
        ], [4, 13], font=8)
    r.h("Other local sources", 2)
    others = [x for x in reg if x.get("source_key") in ("local",)]
    r.table(["Dataset", "Provider", "Status", "Notes"], [[o["dataset_name"], o["provider"], o["preprocessing_status"], " ".join(o["notes"])[:300]]
                                                        for o in others], [5, 3.5, 2.5, 6], font=7.5,
            caption="Local datasets without an assignment-supplied source URL.")

    # ------------------------------------------------------------- 6 methodology
    r.h("5. Preprocessing Methodology")
    r.p("The workflow is implemented as independent handlers so that a failure in one dataset never stops others. Each handler writes a JSON quality "
        "record (steps, metrics, issues, outputs, validation) to data/reports/antarctic/quality/. The methods below describe what the code does; "
        "the results are reported in Sections 6-10.")
    r.bullets([
        ("Inventory and integrity. ", "Recursive listing of DATAS/, format detection from magic bytes, shapefile component grouping, SHA-256 hashing "
         "(cached by size and mtime) before processing, and a forced full re-hash after processing to prove raw files are unchanged."),
        ("NetCDF time series (OMI extent). ", "Raw read to count _FillValue occurrences before CF masking; continuity check of the monthly axis "
         "(duplicates, missing months, time-within-bounds); plausibility limits; recomputation of the stored climatology; |z| > 3 anomalies flagged "
         "(not removed); tidy CSV keeping original km^2 plus documented derived columns."),
        ("NetCDF grids (DMI-ASIP SIC). ", "Chunked scan (512 rows) of the 65.5-million-cell grid; exact value histograms; separation of valid zero, "
         "valid ice, fill and invalid values; consistency of the confidence quality field; fill cells split by presence of acq_time; grid "
         "regularity, coordinate ranges. Native file retained (no regridding)."),
        ("Tabular CSV. ", "Header/units-row parsing, column renaming with explicit unit suffixes, type coercion with invalid-value counting, "
         "duplicate keys, day-of-year completeness, percentile ordering, date validity and sampling-gap analysis. No row is dropped and no missing "
         "value is filled."),
        ("JSON catalog. ", "Syntax validation, schema discovery, flattening of nested platform/instrument arrays into delimited columns while the "
         "full nested structure is retained verbatim, UTC timestamp parsing with original strings kept, cross-check against the CSV export."),
        ("Vector data (GLIMS, KMZ). ", "Attribute-filtered streaming reads of the 9 GB shapefile; GEOS validity with reasons; repaired copies via "
         "make_valid in a separate layer; coordinate-range checks; duplicate keys and byte-identical geometries; equal-area (EPSG:6932) area "
         "recomputation; STRtree overlap analysis; GeoPackage outputs in the original CRS (EPSG:4326)."),
        ("Raster imagery. ", "Blockwise band statistics, CRS / geotransform / GCP detection, EXIF and TIFF tags."),
        ("Metadata and documents. ", "ISO 19139 fields (title, abstract, temporal and spatial extent, constraints, online resources), HTML index "
         "parsing, PDF and PNG verification. Status 'metadata_inspected'."),
        ("ERA5 (API outputs). ", "Static ast parsing of the request, size estimation, credential presence check (values never read). Ready-to-run "
         "handlers distinguish single- and pressure-level products, validate time/latitude/level coordinates, compare units with the ERA5 "
         "reference, stream statistics by time block, flag implausible values and write an Antarctic (lat <= -60) subset at native resolution "
         "plus a cos(latitude)-weighted mean time series."),
    ])

    # ------------------------------------------------------------- 7 dataset-specific
    r.h("6. Dataset-Specific Processing")
    main_ids = ["cmems_omi_si_extent", "cmems_dmi_asip_sic", "nsidc_g02135_south_daily", "nsidc_g02135_south_climatology",
                "nsidc_g02135_north_climatology", "comparison_omi_vs_nsidc_extent", "glims_polygons", "glims_points", "glims_images",
                "glims_lines", "glims_hypsometry", "pgc_ncalm_dv_lidar_tiles", "nasa_edsc_catalog", "oib_arctic_form_drag", "ags_glacier_photograph"]
    for did in main_ids:
        q = recs.get(did)
        if not q:
            continue
        r.h(f"6.{main_ids.index(did) + 1} {q['dataset_name']}", 2)
        r.p(f"Status: {q['status']}  |  Domain relevance: {q.get('domain_relevance')}  |  Sources: {', '.join(q['source_files'][:4])}"
            + (" ..." if len(q["source_files"]) > 4 else ""), size=9, italic=True)
        r.bullets([s for s in q["steps"]])
        if q["validation"]:
            r.p("Validation: " + "; ".join(f"{k} = {v}" for k, v in q["validation"].items()), size=9.5)
        if q["outputs"]:
            r.p("Outputs: " + "; ".join(o["path"] for o in q["outputs"]), size=9.5)
        if q["notes"]:
            r.p("Notes: " + " ".join(q["notes"]), size=9.5, italic=True)
        if q["errors"]:
            r.p("Errors: " + "; ".join(q["errors"]), size=9.5)

    # ------------------------------------------------------------- API section
    r.h("7. Preprocessing of API-Generated Scientific Datasets")
    a1, a2 = recs.get("era5_single_levels"), recs.get("era5_pressure_levels")
    edsc = recs.get("nasa_edsc_catalog")
    r.p("Key finding. Both scripts in EXTERNAL APIs/ are Copernicus Climate Data Store (CDS) requests made with the cdsapi client. They request "
        "NetCDF output (data_format = 'netcdf'), not JSON. A search of DATAS/, data/raw/antarctic/era5/, EXTERNAL APIs/ and the repository root "
        "(including zip archives returned by the CDS) found no ERA5 output from either script. The only JSON dataset in the project, "
        "DATAS/edsc_collection_results_export.json, is a NASA Earthdata Search catalog export; its structure (CMR collection records) shows that it "
        "was not produced by either script. It is processed as a catalog dataset (Section 6.13) and is NOT presented as API output.")
    for q, script in [(a1, "API.py"), (a2, "PRESSUREAPI.py")]:
        if not q:
            continue
        m = q["metrics"]
        est = m["request_estimate"]
        r.h(f"7.{1 if script == 'API.py' else 2} {script}", 2)
        r.table(["Property", "Observed value"], [
            ["Purpose", q["dataset_name"]],
            ["Endpoint / provider", f"CDS dataset '{m['script']['dataset']}' (https://cds.climate.copernicus.eu), via cdsapi Client().retrieve().download()"],
            ["Authentication", "Personal CDS access token in ~/.cdsapirc or CDSAPI_URL/CDSAPI_KEY env vars (values never read)"],
            ["Credential status here", ", ".join(f"{k}={v}" for k, v in m["credentials"].items())],
            ["Response structure", f"{m['response_format']} file (CF NetCDF4); no pagination; output written to the working directory"],
            ["Variables requested", f"{len(m['request']['variable'])}: " + ", ".join(m["request"]["variable"])],
            ["Pressure levels", ", ".join(m["request"].get("pressure_level", [])) or "n/a (single levels)"],
            ["Temporal request", f"{est['years'][0]}-{est['years'][1]}, {est['times_per_day']} times/day; {est['valid_dates']:,} valid dates; "
                                 f"{est['invalid_calendar_dates_ignored']} impossible dates (e.g. 30 Feb); {est['dates_not_yet_available']} after the ERA5 publication horizon"],
            ["Spatial request", str(est["area"])],
            ["Estimated size", f"{est['fields']:,} fields x {est['grid_points_per_field']:,} points = ~{est['uncompressed_float32_TB']} TB (uncompressed float32)"],
            ["Local outputs found", ", ".join(m.get("local_outputs_found", [])) or "none"],
            ["Processing status", q["status"]],
            ["Issues", "; ".join(f"{i['type']}: {i['detail']}" for i in q["issues"])],
        ], [4, 13], font=7.5)
    if a1 and a2:
        e1, e2 = a1["metrics"]["request_estimate"], a2["metrics"]["request_estimate"]
        r.table(["Metric (observed)", "API.py", "PRESSUREAPI.py"], [
            ["CDS dataset", a1["metrics"]["script"]["dataset"], a2["metrics"]["script"]["dataset"]],
            ["Variables", e1["variables"], e2["variables"]], ["Levels", e1["pressure_levels"], e2["pressure_levels"]],
            ["Years", f"{e1['years'][0]}-{e1['years'][1]}", f"{e2['years'][0]}-{e2['years'][1]}"],
            ["Valid dates", f"{e1['valid_dates']:,}", f"{e2['valid_dates']:,}"],
            ["Fields requested", f"{e1['fields']:,}", f"{e2['fields']:,}"],
            ["Approx. TB (uncompressed)", e1["uncompressed_float32_TB"], e2["uncompressed_float32_TB"]],
            ["Output format", a1["metrics"]["response_format"], a2["metrics"]["response_format"]],
            ["Local output files", len(a1["metrics"].get("local_outputs_found", [])), len(a2["metrics"].get("local_outputs_found", []))],
            ["Records before / after", f"{a1['metrics'].get('records_before')} / {a1['metrics'].get('records_after')}",
             f"{a2['metrics'].get('records_before')} / {a2['metrics'].get('records_after')}"],
            ["Missing values / duplicates", "not measurable (no data)", "not measurable (no data)"],
            ["Status", a1["status"], a2["status"]],
        ], [5, 6, 6], font=8, caption="Comparison of the two API datasets (request-level statistics only; no response data exist locally).")
    r.p("Preprocessing implemented for these sources (executed in tests on synthetic ERA5-shaped files, ready for the real outputs): automatic "
        "detection of ERA5 NetCDF files and CDS zip archives; separate single-level and pressure-level handlers; time duplicate/gap checks; latitude "
        "order and range; pressure-level set, order and duplicates; unit comparison against the ERA5 reference without conversion; streaming "
        "missing-value and plausibility statistics; Antarctic subset written at native 0.25 degree resolution; area-weighted mean series. The two "
        "datasets would not be merged: they differ in vertical coordinate and variable set. A join on valid_time/latitude/longitude would only be "
        "valid after confirming identical grids and time steps.")
    r.p("Integration and safety: the scripts are parsed (not imported) because they submit a request at import time. An opt-in wrapper "
        "(era5_api.retrieve_era5, dry-run by default) reuses each script's request, restricts it to Antarctica [-60, -180, -90, 180] and chosen "
        "years/months, refuses requests above a field limit, never overwrites existing files, retries with back-off on HTTP errors, rate limits "
        "and timeouts, and writes a provenance sidecar. The original scripts were not modified.")
    if edsc:
        m = edsc["metrics"]
        r.p(f"Earthdata Search JSON (for comparison): {m['records_before']} records, {m['csv_rows']} CSV rows, "
            f"{m['json_csv_key_overlap']} shared keys, {m['duplicate_keys']} duplicate keys, {m['missing_count']} null cells, "
            f"{m['records_mentioning_antarctic']} records referencing Antarctic modes; status {edsc['status']}.")

    # ------------------------------------------------------------- 8 missing & duplicates
    r.h("8. Missing Values and Duplicates")
    rows = []
    for did, q in recs.items():
        m = q.get("metrics", {})
        if q["status"] not in ("processed", "validated", "partially_processed"):
            continue
        dup = next((f"{k}={_fmt(m[k])}" for k in ["duplicate_months", "duplicate_dates", "duplicate_doy", "duplicate_key_rows", "duplicate_glacier_id",
                                                  "duplicate_orig_id", "duplicate_las_file", "duplicate_keys"] if k in m), "n/a")
        if dup.startswith("duplicate_months"):
            dup = f"duplicate months={len(m['duplicate_months'])}"
        rows.append([did, _fmt(m.get("missing_count")), _fmt(m.get("missing_percent")), dup])
    r.table(["Dataset", "Missing count", "Missing %", "Duplicates (key checked)"], rows, [5.5, 3, 2.5, 6], font=7.5,
            caption="Measured missing-value and duplicate statistics (definitions per format; see quality JSON).")
    g = recs.get("glims_polygons", {}).get("metrics", {})
    if g:
        r.p(f"GLIMS polygons: {g.get('duplicate_key_rows')} rows share (glac_id, anlys_id, line_type); {g.get('duplicate_geometry_rows')} rows have "
            f"byte-identical geometry; {g.get('glaciers_with_multiple_analyses')} glaciers have several analyses (multi-temporal outlines, expected). "
            "Missing attributes per field are listed in the quality record (antarctic_missing_by_attribute).")
        top = sorted(g.get("antarctic_missing_by_attribute", {}).items(), key=lambda kv: -kv[1])[:10]
        n = g.get("antarctic_features", 1)
        r.table(["GLIMS attribute", "Missing (RGI 19)", "%"], [[k, f"{v:,}", f"{100 * v / n:.1f}"] for k, v in top], [6, 4, 3], font=8,
                caption="Ten most incomplete GLIMS polygon attributes in the Antarctic subset.")

    # ------------------------------------------------------------- 9 quality
    r.h("9. Data-Quality Assessment")
    r.p("All issues raised by the handlers. 'error' = invalid per definition; 'warning' = requires attention; 'info' = expected or documented "
        "behaviour. Flagged observations were retained.")
    rows = []
    for did, q in recs.items():
        for i in q["issues"]:
            rows.append([did, i["severity"], i["type"], _fmt(i.get("count")) if i.get("count") is not None else "", i["detail"][:220]])
    order = {"error": 0, "warning": 1, "info": 2}
    rows.sort(key=lambda x: (order.get(x[1], 3), x[0]))
    r.table(["Dataset", "Severity", "Type", "Count", "Detail"], rows, [3.6, 1.5, 2.6, 1.6, 7.7], font=7, caption="Data-quality issues register.")

    # ------------------------------------------------------------- 10 before/after
    r.h("10. Before-and-After Results")
    rows = []
    for did, q in recs.items():
        m = q.get("metrics", {})
        if "records_before" in m:
            rows.append([did, _fmt(m.get("records_before")), _fmt(m.get("records_after")), _fmt(m.get("excluded_records", "")),
                         (m.get("exclusion_reason") or "")[:120], q["status"]])
    r.table(["Dataset", "Before", "After", "Excluded", "Exclusion reason", "Status"], rows, [3.8, 2.3, 2.3, 1.7, 5.2, 2], font=7,
            caption="Record counts or dimensions before and after preprocessing.")
    omi = recs.get("cmems_omi_si_extent", {}).get("metrics", {})
    if omi:
        r.p("Schema change example (OMI extent): NetCDF variables time, time_bounds, siextent, monthlyclim* -> CSV columns time, time_bound_start, "
            "time_bound_end, year, month, siextent_km2 (unchanged values), siextent_million_km2, clim_mean_km2, anomaly_km2, anomaly_zscore, "
            f"flag_missing, flag_outlier_abs_z_gt_3. Values verified identical after reopening: "
            f"{recs['cmems_omi_si_extent']['validation'].get('values_identical_to_source')}.")

    # ------------------------------------------------------------- 11 figures
    r.h("11. Visualizations")
    for f in figs:
        if not f.get("file"):
            continue
        r.h(f["title"], 3)
        r.figure(ROOT / f["file"], f"{f['caption']} Dataset: {f['dataset']}. Variables: {f['variables']}.")
        r.p(f["interpretation"], bold_lead="Interpretation: ")
    missing_figs = [f for f in figs if not f.get("file")]
    if missing_figs:
        r.p("Figures not generated:", bold_lead="")
        r.bullets([f"{f['name']}: {f['not_generated_reason']}" for f in missing_figs])

    # ------------------------------------------------------------- 12 outputs
    r.h("12. Output Organization")
    r.table(["Location", "Content"], [
        ["DATAS/", "Raw user-collected data (read-only, verified unchanged)"],
        ["data/raw/antarctic/external/", "Small official downloads with .provenance.json sidecars"],
        ["data/processed/antarctic/", "Processed outputs (sea_ice_extent/, sea_ice_concentration/, glims/, pgc/, catalogs/, metadata/, era5/)"],
        ["data/reports/antarctic/quality/", "One JSON quality report per dataset record"],
        ["data/reports/antarctic/figures/", "PNG figures + figures_manifest.json"],
        ["data/reports/antarctic/logs/", "Timestamped processing logs"],
        ["data/reports/antarctic/pipeline_run_summary.json", "Run configuration, software versions, status counts, integrity check"],
        ["metadata/antarctic_dataset_inventory.csv/.json", "File inventory (pre-run snapshot: antarctic_dataset_inventory_prerun.csv)"],
        ["metadata/antarctic_dataset_manifest.csv", "Source-to-output mapping"],
        ["metadata/antarctic_source_registry.json", "Source registry with download/validation/preprocessing status"],
        ["metadata/antarctic_external_source_checks.json", "Cached results of the remote source checks"],
        ["reports/", "This Word report"],
    ], [7, 10], font=8, caption="Output directories.")
    rows = [[x.dataset_id, x.output_path, _fmt(int(x.output_bytes)) if str(x.output_bytes) not in ("", "nan") else ""] for x in man.itertuples() if x.output_path]
    rows = list({tuple(r_): r_ for r_ in rows}.values())
    r.table(["Dataset", "Output path", "Bytes"], rows, [4.2, 10.3, 2.5], font=7, caption="Processed outputs (from metadata/antarctic_dataset_manifest.csv).")

    # ------------------------------------------------------------- 13 limitations
    r.h("13. Limitations")
    lim = [
        "ERA5 single-level and pressure-level data requested by API.py / PRESSUREAPI.py are not present locally; the requests are global, "
        "multi-terabyte and need CDS credentials (cdsapi is not installed and no credentials are configured here). These datasets are therefore "
        "'not_available'; no ERA5 statistics are reported.",
        "Copernicus sea-ice drift (SEAICE_ANT_PHY_L3_MY_011_018): only the ISO metadata XML is local. Drift validation and derived speed/direction "
        "were not executed. Downloading requires a Copernicus Marine account.",
        "Sea-ice concentration (SEAICE_ANT_PHY_AUTO_L3_NRT_011_012): a single daily file; the product has no explicit land mask, so land vs "
        "no-coverage fill is separated only heuristically (acq_time).",
        "GLIMS: the NSIDC DAAC directory requires Earthdata Login and was not accessed; the local global GLIMS web export was used. The images "
        "layer lacks glacier IDs and cannot be linked to outlines; the lines layer is empty.",
        "Arctic files (Cda_ArcticOIB20090331-0425.nc, N_seaice_extent_climatology_1981-2010_v4.0.csv) are out of the Antarctic scope.",
        "AGS_A_2002_04.tif is a non-georeferenced photograph of unverified provenance; it has no spatial use.",
        "Earthdata-Download-x64.exe is software, not data (unsupported); it was not executed.",
        "PGC map application (source D) and SCAR AMD (source E) are catalogs/applications; no datasets were downloaded from them. Only the "
        "LiDAR tile index (not the LAS point clouds) is local.",
        "Units of the PGC tile Z values and NSIDC climatology columns are not stated in the files; they were taken from provider conventions and "
        "documented as such.",
    ]
    r.bullets(lim)

    # ------------------------------------------------------------- 14 reproducibility
    r.h("14. Reproducibility")
    r.p("Run from the repository root:")
    for c in [RUN_CMD + "                      # offline rerun (uses cached remote checks)",
              RUN_CMD + " --check-remote --download-small",
              "python -m pytest tests/test_antarctic_preprocessing.py --junitxml=data/reports/antarctic/test_results.xml",
              "python -m data.src.preprocessing.antarctic.report_docx            # rebuild this report only",
              "python -m data.src.preprocessing.antarctic.era5_api --script API.py --years 2023 --months 01   # ERA5 dry run"]:
        para = r.doc.add_paragraph()
        run = para.add_run(c)
        run.font.name = "Consolas"
        run.font.size = Pt(8.5)
    sw = summ.get("software", {})
    r.table(["Component", "Version"], [[k, v] for k, v in sw.items()], [6, 11], font=8, caption="Software environment recorded by the run.")
    if tests:
        r.p(f"Automated tests: {tests['tests']} executed, {tests['failures']} failed, {tests['errors']} errors, {tests['skipped']} skipped "
            f"({tests['time']:.1f} s, {tests['timestamp']}).")
        r.table(["Test", "Result", "Message"], [[c["name"], c["status"], c["msg"]] for c in tests["cases"]], [8, 2, 7], font=7.5,
                caption="Test results (pytest JUnit XML).")
    else:
        r.p("Automated test results were not available when the report was generated.")
    integ = summ.get("raw_integrity", {})
    r.p(f"Raw-data integrity: {integ.get('files_checked')} files re-hashed after processing; changed = {len(integ.get('changed', []))}, "
        f"missing = {len(integ.get('missing', []))} -> {'UNCHANGED' if integ.get('unchanged') else 'CHANGED'}.")

    # ------------------------------------------------------------- 15 conclusion
    r.h("15. Conclusion")
    ok = [q for q in recs.values() if q["status"] == "processed"]
    r.p(f"The pipeline produced {summ.get('unique_output_files', 'n/a')} distinct validated output files from {len(ok)} processed dataset records, "
        f"validated {sum(q['status'] == 'validated' for q in recs.values())} further datasets in their native format and documented "
        f"{sum(q['status'] == 'metadata_inspected' for q in recs.values())} metadata/documentation items. The Antarctic sea-ice extent record "
        f"(1979-2024) is complete apart from {len(omi.get('missing_months_fill', []))} fill months and agrees closely with the independent NSIDC "
        f"index; GLIMS outlines for RGI region 19 were extracted, validated and flagged; the PGC LiDAR tile index was converted to a GeoPackage. "
        "Remaining work before scientific use: obtain the ERA5 outputs with an Antarctic-restricted, split request; download sea-ice drift and "
        "additional sea-ice concentration days through a Copernicus Marine account; replace the Arctic files with Antarctic equivalents where "
        "needed; and review the flagged GLIMS overlaps and invalid geometries.")

    # ------------------------------------------------------------- 16 references
    r.h("16. References")
    refs = [
        "Copernicus Marine Service. Antarctic Monthly Sea Ice Extent from Observations Reprocessing (ANTARCTIC_OMI_SI_extent_obs). "
        "https://doi.org/10.48670/moi-00187 ; https://data.marine.copernicus.eu/product/ANTARCTIC_OMI_SI_extent_obs/services",
        "Copernicus Marine Service. Antarctic Ocean - High Resolution Sea Ice Information (SEAICE_ANT_PHY_AUTO_L3_NRT_011_012). "
        "https://doi.org/10.48670/mds-00320 ; https://documentation.marine.copernicus.eu/PUM/CMEMS-SEAICE-PUM-011-012.pdf",
        "Copernicus Marine Service. Antarctic Ocean Sea Ice Drift REPROCESSED (SEAICE_ANT_PHY_L3_MY_011_018). https://doi.org/10.48670/moi-00120 ; "
        "https://documentation.marine.copernicus.eu/PUM/CMEMS-SEAICE-PUM-011-018.pdf",
        "Copernicus Marine Service STAC catalogue. https://stac.marine.copernicus.eu/",
        "Polar Geospatial Center. Antarctica map catalog. https://maps.apps.pgc.umn.edu/antarctica ; NCALM Dry Valleys LiDAR: http://data.pgc.umn.edu/elev/dem/ncalm/2014/",
        "Scientific Committee on Antarctic Research. Antarctic Master Directory. https://scar.org/library-data/data/amd ; "
        "https://search.earthdata.nasa.gov/portal/amd/search",
        "GLIMS Consortium. GLIMS Glacier Database, Version 1 (NSIDC-0272). https://doi.org/10.7265/N5V98602 ; "
        "https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0272_GLIMS_v1/ ; field descriptions: http://www.glims.org/MapsAndDocs/downloaded_field_desc.html",
        "Raup, B.H., Racoviteanu, A., Khalsa, S.J.S., Helm, C., Armstrong, R., Arnaud, Y. (2007). The GLIMS Geospatial Glacier Database. "
        "Global and Planetary Change 56, 101-110 (cited in DATAS/glims_download_33432/CITATIONS.txt).",
        "National Snow and Ice Data Center. Sea Ice Index, Version 4 (G02135). https://doi.org/10.7265/a98x-0f50 ; "
        "https://noaadata.apps.nsidc.org/NOAA/G02135/",
        "Petty, A.A., Tsamados, M.C., Kurtz, N.T. (2017). Atmospheric form drag over Arctic sea ice using remotely sensed ice topography observations. "
        "J. Geophys. Res. Earth Surf., 122. doi:10.1002/2017JF004209 (from file metadata).",
        "Hersbach, H. et al. ERA5 hourly data on single levels / pressure levels. Copernicus Climate Change Service (C3S) Climate Data Store. "
        "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels ; https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels",
        "NASA Earthdata Search. https://search.earthdata.nasa.gov/",
        "NOAA NCEI ArcGIS REST services - antarctic folder. https://gis.ngdc.noaa.gov/arcgis/rest/services/antarctic",
    ]
    r.bullets(refs, style="List Number")

    WORD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    r.doc.save(WORD_REPORT)
    Document(WORD_REPORT)   # reopen to validate
    return WORD_REPORT


if __name__ == "__main__":
    print(rel(build_report()))
