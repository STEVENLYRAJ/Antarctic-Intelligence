"""Regenerate all artifact-driven documents in docs/ml_task_01/.  python scripts/build_docs.py"""
import _bootstrap

_bootstrap.setup("build_docs")
from aethentra.reporting import docs_data, docs_final, docs_results  # noqa: E402

docs_data.data_inventory()
docs_data.data_sources_and_provenance()
docs_data.data_quality_report()
docs_results.training_report()
docs_results.evaluation_report()
docs_final.model_card()
docs_final.final_report()
print("docs written")
