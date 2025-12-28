"""
Subscription Store Module.

This module provides the SubscriptionStore class, which serves as an in-memory
SQLite database for subscription data. It handles data ingestion from CSV,
schema definition, and exposes secure SQL query tools for agent interaction.
"""

import sqlite3
import csv
from typing import List, Dict, Any, Optional, Callable

from config.tools_config import SUBSCRIPTION_STORE_TOOLS_JSON


class SubscriptionStore:
    """
    In-memory SQLite store for subscription data.

    This class ingests a CSV file into a temporary SQLite database and provides
    methods to retrieve tool schemas and execute SQL queries securely.
    """
    def __init__(self, csv_path: str):
        """
        Initialize the SubscriptionStore.

        Args:
            csv_path (str): The file path to the subscription data CSV.
        """
        # Using check_same_thread=False could allow this to work in multi-threaded web frameworks
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._init_db(csv_path)

    def _init_db(self, csv_path: str):
        """
        Initialize the database schema and ingest data from the CSV file.

        Args:
            csv_path (str): The file path to the subscription data CSV.

        Raises:
            FileNotFoundError: If the specified CSV file cannot be found.
        """
        cursor = self.connection.cursor()

        # Define Schema
        cursor.execute("""
            CREATE TABLE subscriptions (
                subscription_id TEXT PRIMARY KEY,
                company_name TEXT,
                plan_tier TEXT,
                monthly_revenue REAL,
                annual_revenue REAL,
                start_date TEXT,
                end_date TEXT,
                status TEXT,
                seats_purchased INTEGER,
                seats_used INTEGER,
                industry TEXT,
                primary_contact TEXT,
                payment_method TEXT,
                auto_renew BOOLEAN,
                last_payment_date TEXT,
                outstanding_balance REAL,
                support_tier TEXT,
                implementation_date TEXT,
                custom_features TEXT
            )
        """)

        # Ingest Data
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = []
                for row in reader:
                    data.append((
                        row['subscription_id'],
                        row['company_name'],
                        row['plan_tier'],
                        float(row['monthly_revenue']) if row['monthly_revenue'] else 0.0,
                        float(row['annual_revenue']) if row['annual_revenue'] else 0.0,
                        row['start_date'],
                        row['end_date'],
                        row['status'],
                        int(row['seats_purchased']) if row['seats_purchased'] else 0,
                        int(row['seats_used']) if row['seats_used'] else 0,
                        row['industry'],
                        row['primary_contact'],
                        row['payment_method'],
                        1 if str(row['auto_renew']).lower() in ['true', 'yes', '1'] else 0,
                        row['last_payment_date'],
                        float(row['outstanding_balance']) if row['outstanding_balance'] else 0.0,
                        row['support_tier'],
                        row['implementation_date'],
                        row['custom_features']
                    ))
            cursor.executemany("""
                INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, data)
            self.connection.commit()
        except FileNotFoundError:
            print(f"Warning: File {csv_path} not found. Database is empty.")

    def get_tools(self) -> Dict[str, Callable]:
        """
        Get the mapping of tool names to their implementation functions.

        Returns:
            Dict[str, Callable]: A dictionary where keys are tool names and
            values are the corresponding methods.
        """
        return {
            "get_database_schema": self.get_database_schema,
            "run_sql_query": self.run_sql_query
        }

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Get the JSON schemas for the tools exposed by this store.

        Returns:
            List[Dict[str, Any]]: A list of tool definitions compatible with
            the Cohere API.
        """
        return SUBSCRIPTION_STORE_TOOLS_JSON

    def get_database_schema(self) -> str:
        """
        Retrieve the schema definition of the subscriptions table.

        Returns:
            str: A formatted string listing the table name and its columns.
        """
        cursor = self.connection.execute("PRAGMA table_info(subscriptions)")
        columns = [row['name'] for row in cursor.fetchall()]
        return f"Table: subscriptions\nColumns: {', '.join(columns)}"

    def run_sql_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a read-only SQL query against the database.

        Args:
            query (str): The SQL query string to execute.

        Returns:
            List[Dict[str, Any]]: A list of records resulting from the query,
            or a list containing an error dictionary if the query fails or is forbidden.
        """
        # Safety block - banlist of words
        forbidden = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER"]
        if any(w in query.upper() for w in forbidden):
            return [{"error": "Security Alert: Read-only access."}]

        # Execute otherwise
        try:
            cursor = self.connection.execute(query)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            # Return the error text so the Agent can self-correct
            return [{"error": f"SQL Syntax Error: {str(e)}"}]
