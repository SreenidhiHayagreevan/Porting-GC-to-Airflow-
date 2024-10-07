# -*- coding: utf-8 -*-
"""Airflow

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1_vUUVnZJ9mS5eA8E7ZbRdM7tVfJTfrIB
"""

from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from datetime import datetime
import requests

# Function to establish Snowflake connection
def return_snowflake_conn():
    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')
    conn = hook.get_conn()
    return conn.cursor()

# Task to extract stock market data from Alpha Vantage API
@task
def extract(symbol: str):
    api_key = Variable.get("alpha_url")  # Alpha Vantage API key saved in Airflow variables
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={api_key}"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception(f"Error fetching data: {response.status_code}")

    data = response.json()
    if "Time Series (Daily)" not in data:
        raise KeyError(f"Invalid response from Alpha Vantage: {data}")

    return data["Time Series (Daily)"]

# Task to transform the extracted stock data (last 90 days)
@task
def transform(time_series: dict, symbol: str):
    results = []
    for date, stock_info in list(time_series.items())[-90:]:  # Last 90 days
        stock_info["6. date"] = date
        stock_info["7. symbol"] = symbol
        results.append(stock_info)
    return results

# Task to load transformed data into Snowflake
@task
def load(records, target_table: str):
    cur = return_snowflake_conn()
    try:
        cur.execute("BEGIN")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {target_table} (
                open float,
                high float,
                low float,
                close float,
                volume integer,
                symbol varchar,
                date date,
                PRIMARY KEY (symbol, date)
            )
        """)

        for record in records:
            open_price = record['1. open'].replace("'", "''")
            high_price = record['2. high'].replace("'", "''")
            low_price = record['3. low'].replace("'", "''")
            close_price = record['4. close'].replace("'", "''")
            volume = record['5. volume'].replace("'", "''")
            date = record['6. date'].replace("'", "''")
            symbol = record['7. symbol'].replace("'", "''")

            sql = f"""
                INSERT INTO {target_table} (open, high, low, close, volume, date, symbol)
                VALUES ('{open_price}', '{high_price}', '{low_price}', '{close_price}', '{volume}', '{date}', '{symbol}')
            """
            cur.execute(sql)

        cur.execute("COMMIT")
    except Exception as e:
        cur.execute("ROLLBACK")
        raise e

# Define the DAG
with DAG(
    dag_id='stock_market_etl',
    start_date=datetime(2024, 10, 1),
    catchup=False,
    schedule_interval='30 2 * * *',  # Run daily at 2:30 AM
    tags=['stock', 'ETL'],
) as dag:

    # DAG parameters
    stock_symbol = "ISRG"
    target_table = "dev.raw_data.stock_price"

    # Task dependencies
    extracted_data = extract(stock_symbol)
    transformed_data = transform(extracted_data, stock_symbol)
    load(transformed_data, target_table)