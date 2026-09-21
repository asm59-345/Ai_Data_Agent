import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.etl_tools import ETLTools


def test_etl_extract_load(tmp_path):
    etl = ETLTools()
    target_folder = str(tmp_path / "extract")
    
    # Test extraction with a stable public JSON endpoint
    result = etl.extract_load(
        url="https://jsonplaceholder.typicode.com/todos/1",
        output_folder=target_folder,
        format="json"
    )
    assert "Success" in result
    assert os.path.exists(os.path.join(target_folder, "extracted_data.json"))


def test_etl_code_execution():
    etl = ETLTools()
    code = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
print(f"SUM_A={df['a'].sum()}")
"""
    result = etl.execute_code(code)
    assert "Execution completed successfully." in result
    assert "SUM_A=6" in result
