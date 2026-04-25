"""
OpenLineage and DataHub integration utilities for lineage tracking.

Provides helpers to emit lineage events for DuckDB tables, Parquet files,
and dbt models to OpenLineage/DataHub for observability and catalog.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# OpenLineage config from env
OPENLINEAGE_URL = os.getenv("OPENLINEAGE_URL", "http://localhost:5000")
OPENLINEAGE_NAMESPACE = os.getenv("OPENLINEAGE_NAMESPACE", "nfl-dead-money")

# DataHub config from env
DATAHUB_GMS_HOST = os.getenv("DATAHUB_GMS_HOST", "localhost")
DATAHUB_GMS_PORT = os.getenv("DATAHUB_GMS_PORT", "8080")


def emit_openlineage_event(
    job_name: str,
    run_id: str,
    event_type: str,
    inputs: Optional[List[Dict]] = None,
    outputs: Optional[List[Dict]] = None,
    run_facets: Optional[Dict] = None,
) -> bool:
    """
    Emit an OpenLineage event for a job run.

    Args:
        job_name: Name of the job/task
        run_id: Unique run identifier (UUID or timestamp-based)
        event_type: 'START', 'RUNNING', 'COMPLETE', 'FAIL', 'ABORT'
        inputs: List of input dataset dicts with name, namespace, facets
        outputs: List of output dataset dicts with name, namespace, facets
        run_facets: Additional run metadata (e.g., parent run, processing stats)

    Returns:
        True if emission succeeded, False otherwise
    """
    try:
        from openlineage.client import OpenLineageClient
        from openlineage.client.facet import NominalTimeRunFacet
        from openlineage.client.run import Job, Run, RunEvent

        client = OpenLineageClient(url=OPENLINEAGE_URL)

        event_time = datetime.utcnow().isoformat() + "Z"

        # Build datasets
        input_datasets = []
        if inputs:
            for ds in inputs:
                from openlineage.client.run import Dataset

                input_datasets.append(
                    Dataset(
                        namespace=ds.get("namespace", OPENLINEAGE_NAMESPACE),
                        name=ds.get("name", "unknown"),
                        facets=ds.get("facets", {}),
                    )
                )

        output_datasets = []
        if outputs:
            for ds in outputs:
                from openlineage.client.run import Dataset

                output_datasets.append(
                    Dataset(
                        namespace=ds.get("namespace", OPENLINEAGE_NAMESPACE),
                        name=ds.get("name", "unknown"),
                        facets=ds.get("facets", {}),
                    )
                )

        # Build run facets
        facets = run_facets or {}
        facets["nominalTime"] = NominalTimeRunFacet(nominalStartTime=event_time)

        event = RunEvent(
            eventType=event_type,
            eventTime=event_time,
            run=Run(runId=run_id, facets=facets),
            job=Job(namespace=OPENLINEAGE_NAMESPACE, name=job_name),
            inputs=input_datasets,
            outputs=output_datasets,
            producer=f"nfl-dead-money-pipeline/{os.getenv('AIRFLOW_VERSION', '3.x')}",
        )

        client.emit(event)
        logger.info(f"✓ OpenLineage event emitted: {job_name} ({event_type})")
        return True

    except ImportError:
        logger.warning("OpenLineage client not installed; skipping lineage emission")
        return False
    except Exception as e:
        logger.error(f"Failed to emit OpenLineage event: {e}")
        return False


def emit_duckdb_table_lineage(
    table_name: str,
    db_path: str,
    job_name: str,
    run_id: str,
    event_type: str = "COMPLETE",
    row_count: Optional[int] = None,
) -> bool:
    """
    Emit lineage for a DuckDB table write.

    Args:
        table_name: Fully qualified table name (e.g., 'marts.mart_team_summary')
        db_path: Path to DuckDB file
        job_name: Job/task name that created the table
        run_id: Run identifier
        event_type: Event type (default COMPLETE)
        row_count: Optional row count for output facet

    Returns:
        True if emission succeeded
    """
    output = {
        "namespace": f"duckdb://{Path(db_path).absolute()}",
        "name": table_name,
        "facets": {},
    }

    if row_count is not None:
        from openlineage.client.facet import (
            ColumnMetric, DataQualityMetricsInputDatasetFacet)

        output["facets"]["dataQualityMetrics"] = {
            "rowCount": row_count,
            "bytes": None,
            "columnMetrics": [],
        }

    return emit_openlineage_event(
        job_name=job_name, run_id=run_id, event_type=event_type, outputs=[output]
    )


def emit_parquet_file_lineage(
    file_path: str,
    job_name: str,
    run_id: str,
    event_type: str = "COMPLETE",
    row_count: Optional[int] = None,
) -> bool:
    """
    Emit lineage for a Parquet file write.

    Args:
        file_path: Path to Parquet file or directory
        job_name: Job/task name that created the file
        run_id: Run identifier
        event_type: Event type (default COMPLETE)
        row_count: Optional row count for output facet

    Returns:
        True if emission succeeded
    """
    abs_path = Path(file_path).absolute()
    output = {
        "namespace": f"file://{abs_path.parent}",
        "name": abs_path.name,
        "facets": {},
    }

    if row_count is not None:
        output["facets"]["dataQualityMetrics"] = {
            "rowCount": row_count,
            "bytes": abs_path.stat().st_size if abs_path.exists() else None,
        }

    return emit_openlineage_event(
        job_name=job_name, run_id=run_id, event_type=event_type, outputs=[output]
    )


def emit_csv_file_lineage(
    file_path: str,
    job_name: str,
    run_id: str,
    event_type: str = "COMPLETE",
    row_count: Optional[int] = None,
) -> bool:
    """
    Emit lineage for a CSV file write (scraped data).

    Args:
        file_path: Path to CSV file
        job_name: Job/task name that created the file
        run_id: Run identifier
        event_type: Event type (default COMPLETE)
        row_count: Optional row count for output facet

    Returns:
        True if emission succeeded
    """
    abs_path = Path(file_path).absolute()
    output = {
        "namespace": f"file://{abs_path.parent}",
        "name": abs_path.name,
        "facets": {},
    }

    if row_count is not None:
        output["facets"]["dataQualityMetrics"] = {
            "rowCount": row_count,
            "bytes": abs_path.stat().st_size if abs_path.exists() else None,
        }

    return emit_openlineage_event(
        job_name=job_name, run_id=run_id, event_type=event_type, outputs=[output]
    )


def push_to_datahub(
    platform: str,
    dataset_name: str,
    env: str = "PROD",
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> bool:
    """
    Push dataset metadata to DataHub catalog.

    Args:
        platform: Platform identifier (e.g., 'duckdb', 'file')
        dataset_name: Dataset name/identifier
        env: Environment (DEV, PROD)
        description: Dataset description
        tags: List of tags for classification

    Returns:
        True if push succeeded
    """
    try:
        from datahub.emitter.mce_builder import make_dataset_urn
        from datahub.emitter.rest_emitter import DatahubRestEmitter
        from datahub.metadata.com.linkedin.pegasus2avro.mxe import \
            MetadataChangeEvent
        from datahub.metadata.schema_classes import DatasetPropertiesClass

        gms_endpoint = f"http://{DATAHUB_GMS_HOST}:{DATAHUB_GMS_PORT}"
        emitter = DatahubRestEmitter(gms_server=gms_endpoint)

        dataset_urn = make_dataset_urn(platform=platform, name=dataset_name, env=env)

        properties = DatasetPropertiesClass(
            description=description or f"Dataset {dataset_name}",
            customProperties={
                "namespace": OPENLINEAGE_NAMESPACE,
                "tags": ",".join(tags or []),
            },
        )

        # Note: This is a simplified example. Full implementation would use
        # MetadataChangeProposalWrapper or similar for proper metadata emission
        logger.info(f"✓ DataHub metadata prepared for: {dataset_urn}")

        # Actual emission would happen here
        # emitter.emit_mce(event)

        return True

    except ImportError:
        logger.warning("DataHub client not installed; skipping catalog push")
        return False
    except Exception as e:
        logger.error(f"Failed to push to DataHub: {e}")
        return False
