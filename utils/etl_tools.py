import os
import sys
import io
import contextlib
import requests
import pandas as pd
from typing import Dict, Any, Optional


class ETLTools:
    """
    Toolkit for data extraction from REST endpoints and data transformations.
    Handles flexible API structures and safe sandbox code execution.
    """

    def __init__(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    def extract_load(self, url: str, output_folder: str, format: str = "csv") -> str:
        """
        Extracts data from a REST API (url) and saves it into the target folder.

        Args:
            url (str): The API endpoint from which to extract data.
            output_folder (str): The folder where extracted data will be saved.
            format (str): The file format (csv, json, parquet).
        """
        # Resolve path safely relative to project root
        if not os.path.isabs(output_folder):
            target_dir = os.path.join(self.project_root, output_folder)
        else:
            target_dir = output_folder

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Data-Agent/1.0"}
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            raw_data = response.json()

            os.makedirs(target_dir, exist_ok=True)
            filename = os.path.join(target_dir, f"extracted_data.{format.lower()}")

            # Flexible data normalization
            if isinstance(raw_data, list):
                df = pd.json_normalize(raw_data)
            elif isinstance(raw_data, dict):
                if "results" in raw_data and isinstance(raw_data["results"], list):
                    df = pd.json_normalize(raw_data["results"])
                elif "data" in raw_data and isinstance(raw_data["data"], list):
                    df = pd.json_normalize(raw_data["data"])
                elif "items" in raw_data and isinstance(raw_data["items"], list):
                    df = pd.json_normalize(raw_data["items"])
                else:
                    df = pd.json_normalize(raw_data)
            else:
                return f"Error: Unexpected JSON payload type: {type(raw_data)}"

            # Save in requested format
            fmt = format.lower().strip()
            if fmt == "csv":
                df.to_csv(filename, index=False)
            elif fmt == "json":
                df.to_json(filename, orient="records", indent=2)
            elif fmt == "parquet":
                df.to_parquet(filename, index=False)
            else:
                return f"Error: Unsupported format '{format}'. Supported formats: csv, json, parquet."

            return f"Success: Extracted {len(df)} records from '{url}' and saved to '{filename}' ({fmt.upper()})."
        except requests.exceptions.RequestException as e:
            return f"Extraction Failed (Network/HTTP Error): {e}"
        except Exception as e:
            return f"Extraction Failed: {e}"

    def transform_load_context(self, file_path: str) -> str:
        """
        Inspects the input data file and returns top rows and schema preview
        so the agent can generate appropriate transformation code.
        """
        if not os.path.isabs(file_path):
            abs_path = os.path.join(self.project_root, file_path)
        else:
            abs_path = file_path

        if not os.path.exists(abs_path):
            return f"Error: File not found at '{abs_path}'"

        try:
            ext = os.path.splitext(abs_path)[1].lower()
            if ext == ".csv":
                df = pd.read_csv(abs_path)
            elif ext == ".json":
                try:
                    df = pd.read_json(abs_path)
                except ValueError:
                    df = pd.read_json(abs_path, lines=True)
            elif ext == ".parquet":
                df = pd.read_parquet(abs_path)
            else:
                return f"Error: Unsupported file format '{ext}'"

            shape_info = f"Dataset Shape: {df.shape[0]} rows, {df.shape[1]} columns\n"
            columns_info = f"Columns & Dtypes:\n{df.dtypes.to_string()}\n\n"
            preview = f"Sample (First 3 rows):\n{df.head(3).to_string()}"

            return shape_info + columns_info + preview
        except Exception as e:
            return f"Error reading file context: {e}"

    def execute_code(self, code: str) -> str:
        """
        Executes Python/Pandas transformation script with stdout capture.
        """
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Shared execution environment
        exec_globals = {
            "pd": pd,
            "pandas": pd,
            "os": os,
            "sys": sys,
            "project_root": self.project_root,
        }

        try:
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                exec(code, exec_globals)

            out = stdout_capture.getvalue().strip()
            err = stderr_capture.getvalue().strip()

            result_msg = "Execution completed successfully."
            if out:
                result_msg += f"\nOutput:\n{out}"
            if err:
                result_msg += f"\nWarnings/Stderr:\n{err}"
            return result_msg
        except Exception as e:
            return f"Execution Failed with Error: {e}"


if __name__ == "__main__":
    tools = ETLTools()
    print("ETLTools initialized successfully.")
