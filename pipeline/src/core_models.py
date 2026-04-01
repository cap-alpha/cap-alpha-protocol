#!/usr/bin/env python3
"""
Core Data Models & Idempotency Framework

Foundation for production-level, idempotent Airflow pipeline.

Design Principles:
1. All records have checksums (MD5 of key fields)
2. Deduplication before processing
3. State tracking (processed_at, processed_by, pipeline_version)
4. Validation gates (pre/post processing)
5. Rollback-safe (idempotent design, no mutations)

Usage:
    from src.core_models import DataRecord, ProcessingState, ValidationGate
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    """Pipeline processing status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ValidationStatus(Enum):
    """Data validation status"""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class ProcessingState:
    """Track processing state for idempotency"""

    processed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    processed_by: str = "airflow_pipeline"
    pipeline_version: str = "1.0"
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: Optional[str] = None
    row_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "processed_at": self.processed_at,
            "processed_by": self.processed_by,
            "pipeline_version": self.pipeline_version,
            "status": self.status.value,
            "error_message": self.error_message,
            "row_count": self.row_count,
            "duplicate_count": self.duplicate_count,
            "skipped_count": self.skipped_count,
        }


@dataclass
class ValidationResult:
    """Validation result with details"""

    status: ValidationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    failed_records: List[Dict] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Check if validation passed"""
        return self.status in [ValidationStatus.PASS, ValidationStatus.WARN]


class ChecksumGenerator:
    """Generate checksums for dedup detection"""

    @staticmethod
    def generate_record_checksum(record: Dict[str, Any], key_fields: List[str]) -> str:
        """
        Generate MD5 checksum from key fields

        Args:
            record: Dictionary of record data
            key_fields: Fields to include in checksum (order matters)

        Returns:
            MD5 hex digest
        """
        # Extract key fields in order, convert to strings
        values = []
        for field in key_fields:
            val = record.get(field, "")
            # Normalize: lowercase strings, handle nulls
            if pd.isna(val):
                val = ""
            elif isinstance(val, (int, float)):
                val = str(val)
            else:
                val = str(val).lower().strip()
            values.append(val)

        # Create checksum
        combined = "|".join(values)
        return hashlib.md5(combined.encode()).hexdigest()

    @staticmethod
    def generate_dataframe_checksum(df: pd.DataFrame) -> str:
        """
        Generate overall checksum for entire DataFrame

        Useful for tracking if data changed between runs
        """
        # Sort by all columns for consistency
        df_sorted = df.sort_values(by=list(df.columns)).reset_index(drop=True)

        # Convert to JSON string
        data_str = json.dumps(
            df_sorted.to_dict(orient="records"), default=str, sort_keys=True
        )

        return hashlib.md5(data_str.encode()).hexdigest()


class DeduplicationEngine:
    """
    Detect and handle duplicate records

    Strategy:
    1. Calculate checksums on key fields
    2. Identify duplicates by checksum
    3. Keep first occurrence, mark others as duplicates
    4. Log duplicate findings
    """

    def __init__(self, key_fields: List[str]):
        """
        Initialize dedup engine

        Args:
            key_fields: Fields that uniquely identify a record
                       e.g., ['player_name', 'team', 'year']
        """
        self.key_fields = key_fields

    def detect_duplicates(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Detect and separate duplicates from clean data

        Returns:
            Tuple of (clean_df, duplicates_df)
        """
        if df.empty:
            return df, pd.DataFrame()

        df = df.copy()

        # Generate checksums
        df["_checksum"] = df.apply(
            lambda row: ChecksumGenerator.generate_record_checksum(
                row.to_dict(), self.key_fields
            ),
            axis=1,
        )

        # Identify duplicates (checksum appears >1 time)
        duplicate_mask = df["_checksum"].duplicated(keep="first")

        clean = df[~duplicate_mask].drop("_checksum", axis=1).reset_index(drop=True)
        duplicates = df[duplicate_mask].drop("_checksum", axis=1).reset_index(drop=True)

        logger.info(
            f"  Deduplication: {len(clean)} unique, {len(duplicates)} duplicates removed"
        )

        if len(duplicates) > 0:
            logger.warning(f"  Duplicate records found:")
            for _, dup in duplicates.iterrows():
                key_str = " | ".join([str(dup.get(k, "")) for k in self.key_fields])
                logger.warning(f"    {key_str}")

        return clean, duplicates

    def mark_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Mark duplicates instead of removing them (for audit trail)

        Adds column: is_duplicate (True/False)
        """
        df = df.copy()

        df["_checksum"] = df.apply(
            lambda row: ChecksumGenerator.generate_record_checksum(
                row.to_dict(), self.key_fields
            ),
            axis=1,
        )

        df["is_duplicate"] = df.duplicated(subset=["_checksum"], keep="first")
        df.drop("_checksum", axis=1, inplace=True)

        return df


class ValidationGate:
    """
    Pre/post processing validation gates

    Ensures data quality before moving to next stage
    """

    @staticmethod
    def validate_required_columns(
        df: pd.DataFrame, required_cols: List[str]
    ) -> ValidationResult:
        """Check all required columns present"""
        missing = [c for c in required_cols if c not in df.columns]

        if missing:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                message=f"Missing required columns: {missing}",
                details={"missing_columns": missing},
            )

        return ValidationResult(
            status=ValidationStatus.PASS,
            message=f"All {len(required_cols)} required columns present",
        )

    @staticmethod
    def validate_no_nulls(
        df: pd.DataFrame, critical_cols: List[str]
    ) -> ValidationResult:
        """Check critical columns have no nulls"""
        nulls = {}
        for col in critical_cols:
            if col in df.columns:
                null_count = df[col].isna().sum()
                if null_count > 0:
                    nulls[col] = int(null_count)

        if nulls:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                message=f"Null values found in critical columns: {nulls}",
                details={"null_columns": nulls},
            )

        return ValidationResult(
            status=ValidationStatus.PASS,
            message=f"No nulls in {len(critical_cols)} critical columns",
        )

    @staticmethod
    def validate_data_types(
        df: pd.DataFrame, type_map: Dict[str, str]
    ) -> ValidationResult:
        """Validate column data types"""
        errors = {}
        for col, expected_type in type_map.items():
            if col not in df.columns:
                continue

            if expected_type == "numeric":
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors[col] = f"Expected numeric, got {df[col].dtype}"
            elif expected_type == "string":
                if not pd.api.types.is_object_dtype(
                    df[col]
                ) and not pd.api.types.is_string_dtype(df[col]):
                    errors[col] = f"Expected string, got {df[col].dtype}"

        if errors:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                message=f"Type validation failed: {errors}",
                details={"type_errors": errors},
            )

        return ValidationResult(
            status=ValidationStatus.PASS,
            message=f"All {len(type_map)} columns have correct types",
        )

    @staticmethod
    def validate_value_ranges(
        df: pd.DataFrame, ranges: Dict[str, Tuple[float, float]]
    ) -> ValidationResult:
        """Validate numeric columns within expected ranges"""
        errors = {}
        for col, (min_val, max_val) in ranges.items():
            if col not in df.columns:
                continue

            out_of_range = (df[col] < min_val) | (df[col] > max_val)
            if out_of_range.any():
                count = out_of_range.sum()
                errors[col] = f"{count} values outside [{min_val}, {max_val}]"

        if errors:
            return ValidationResult(
                status=ValidationStatus.WARN,
                message=f"Values outside expected ranges: {errors}",
                details={"range_errors": errors},
            )

        return ValidationResult(
            status=ValidationStatus.PASS, message=f"All values within expected ranges"
        )

    @staticmethod
    def validate_uniqueness(
        df: pd.DataFrame, unique_cols: List[str]
    ) -> ValidationResult:
        """Validate columns are unique"""
        duplicates = df.duplicated(subset=unique_cols, keep=False).sum()

        if duplicates > 0:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                message=f"{duplicates} duplicate records on columns: {unique_cols}",
                details={"duplicate_count": int(duplicates)},
            )

        return ValidationResult(
            status=ValidationStatus.PASS, message=f"All records unique on {unique_cols}"
        )


class IdempotentProcessor:
    """
    Base class for idempotent processing

    Ensures:
    - State tracking
    - Deduplication
    - Validation gates
    - Rollback safety
    """

    def __init__(self, name: str, key_fields: List[str]):
        self.name = name
        self.key_fields = key_fields
        self.dedup_engine = DeduplicationEngine(key_fields)
        self.state = ProcessingState()

    def process(
        self,
        df: pd.DataFrame,
        required_cols: List[str],
        critical_null_cols: List[str] = None,
        unique_on: List[str] = None,
    ) -> Tuple[pd.DataFrame, ProcessingState]:
        """
        Process data with validation gates and dedup

        Args:
            df: Input DataFrame
            required_cols: Columns that must exist
            critical_null_cols: Columns that cannot have nulls
            unique_on: Columns that must be unique

        Returns:
            Tuple of (processed_df, processing_state)
        """
        if critical_null_cols is None:
            critical_null_cols = self.key_fields

        logger.info(f"\n[{self.name}] Processing {len(df)} records...")
        self.state.row_count = len(df)

        # Pre-processing validation
        logger.info(f"  [Gate 1] Validating schema...")
        gate1 = ValidationGate.validate_required_columns(df, required_cols)
        if not gate1.is_valid():
            self.state.status = ProcessingStatus.FAILED
            self.state.error_message = gate1.message
            logger.error(f"  ✗ {gate1.message}")
            return df, self.state
        logger.info(f"  ✓ {gate1.message}")

        # Check for nulls
        if critical_null_cols:
            logger.info(f"  [Gate 2] Validating no nulls in critical columns...")
            gate2 = ValidationGate.validate_no_nulls(df, critical_null_cols)
            if not gate2.is_valid():
                logger.warning(f"  ⚠ {gate2.message}")
            else:
                logger.info(f"  ✓ {gate2.message}")

        # Deduplication
        logger.info(f"  [Gate 3] Deduplicating...")
        clean_df, duplicates_df = self.dedup_engine.detect_duplicates(df)
        self.state.duplicate_count = len(duplicates_df)

        # Check uniqueness if requested
        if unique_on:
            logger.info(f"  [Gate 4] Validating uniqueness on {unique_on}...")
            gate4 = ValidationGate.validate_uniqueness(clean_df, unique_on)
            if not gate4.is_valid():
                self.state.status = ProcessingStatus.FAILED
                self.state.error_message = gate4.message
                logger.error(f"  ✗ {gate4.message}")
                return clean_df, self.state
            logger.info(f"  ✓ {gate4.message}")

        # Success
        self.state.status = ProcessingStatus.COMPLETED
        logger.info(
            f"✓ [{self.name}] Complete: {len(clean_df)} records (removed {self.state.duplicate_count} duplicates)"
        )

        return clean_df, self.state


def create_audit_log(
    df: pd.DataFrame, state: ProcessingState, stage: str, output_dir: Path
) -> Path:
    """
    Create audit log of processing

    Args:
        df: Processed DataFrame
        state: ProcessingState with metadata
        stage: Pipeline stage name
        output_dir: Where to write audit log

    Returns:
        Path to audit log file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    audit_file = output_dir / f"audit_{stage}_{timestamp}.json"

    audit = {
        "stage": stage,
        "timestamp": state.processed_at,
        "processing_state": state.to_dict(),
        "data_checksum": ChecksumGenerator.generate_dataframe_checksum(df),
        "row_count": len(df),
        "columns": list(df.columns),
    }

    with open(audit_file, "w") as f:
        json.dump(audit, f, indent=2, default=str)

    logger.info(f"  Audit log: {audit_file.name}")

    return audit_file
