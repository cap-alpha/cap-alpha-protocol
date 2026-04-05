import unittest

try:
    from airflow.models import DagBag

    HAS_AIRFLOW = True
except ImportError:
    HAS_AIRFLOW = False
from pathlib import Path


@unittest.skipIf(not HAS_AIRFLOW, "Airflow not installed")
class TestDagIntegrity(unittest.TestCase):
    def setUp(self):
        self.dagbag = DagBag(
            dag_folder=str(Path(__file__).parents[1] / "dags"), include_examples=False
        )

    def test_import_dags(self):
        """Verify that Airflow can import the DAGs without errors."""
        self.assertFalse(
            len(self.dagbag.import_errors),
            f"DAG import failures. Errors: {self.dagbag.import_errors}",
        )

    def test_pipeline_loaded(self):
        """Verify specifically that the main pipeline is loaded."""
        dag = self.dagbag.get_dag(dag_id="pipeline")
        self.assertIsNotNone(dag)
        self.assertEqual(len(dag.tasks), 19)  # 19 production tasks


if __name__ == "__main__":
    unittest.main()
