"""Load NFL play-by-play and participation data into Unity Catalog Delta tables.

Uses nflreadpy to download data and databricks-connect to write via Spark.
Works from any local IDE with a configured Databricks profile.
"""

import os
from pathlib import Path


# Columns that cause schema issues and aren't needed
PBP_DROP_COLUMNS = [
    'lateral_sack_player_id', 'lateral_sack_player_name',
    'tackle_for_loss_2_player_id', 'tackle_for_loss_2_player_name',
    'st_play_type', 'end_yard_line',
]


def load_nfl_data(catalog: str, schema: str, seasons: list = None, profile: str = None):
    """Load NFL data into UC Delta tables.

    Args:
        catalog: UC catalog name
        schema: UC schema name
        seasons: List of seasons to load (default: [2022, 2023, 2024])
        profile: Databricks CLI profile for databricks-connect
    """
    if seasons is None:
        seasons = [2022, 2023, 2024]

    # Set profile for databricks-connect
    if profile:
        os.environ['DATABRICKS_CONFIG_PROFILE'] = profile

    import polars as pl
    import pandas as pd
    import nflreadpy as nfl
    from databricks.connect import DatabricksSession

    print(f'  Connecting to Databricks via databricks-connect (serverless)...')
    spark = DatabricksSession.builder.profile(profile or 'DEFAULT').serverless().getOrCreate()
    print(f'  Connected')

    def write_delta(df_pl: pl.DataFrame, table_name: str):
        """Write a Polars DataFrame to a Delta table."""
        full_name = f'{catalog}.{schema}.{table_name}'
        print(f'  Writing {full_name}...')
        pdf = df_pl.to_pandas()
        sdf = spark.createDataFrame(pdf)
        (sdf.write
            .format('delta')
            .mode('overwrite')
            .option('overwriteSchema', 'true')
            .saveAsTable(full_name))
        count = sdf.count()
        print(f'  Wrote {full_name} ({count:,} rows)')

    # Load play-by-play data
    print(f'  Downloading play-by-play data for seasons {seasons}...')
    pbp = nfl.load_pbp(seasons)
    print(f'  Downloaded {pbp.shape[0]:,} plays')

    # Drop problematic columns
    existing_drops = [c for c in PBP_DROP_COLUMNS if c in pbp.columns]
    if existing_drops:
        pbp = pbp.drop(existing_drops)

    write_delta(pbp, 'football_pbp_data')

    # Load participation data
    print(f'  Downloading participation data for seasons {seasons}...')
    participation = nfl.load_participation(seasons)
    print(f'  Downloaded {participation.shape[0]:,} participation records')

    write_delta(participation, 'football_participation')

    print(f'\n  Data loading complete: {catalog}.{schema}')
    return True


if __name__ == '__main__':
    import json
    import sys

    config_path = Path(__file__).resolve().parents[1] / 'config' / 'dc_assistant.json'
    if not config_path.exists():
        print(f'Config not found: {config_path}')
        sys.exit(1)

    config = json.loads(config_path.read_text())
    profile = os.environ.get('DATABRICKS_CONFIG_PROFILE')

    load_nfl_data(
        catalog=config['workspace']['catalog'],
        schema=config['workspace']['schema'],
        seasons=config.get('data_collection', {}).get('seasons', [2022, 2023, 2024]),
        profile=profile,
    )
