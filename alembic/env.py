from __future__ import with_statement

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
try:
    if config.config_file_name and os.path.exists(config.config_file_name):
        fileConfig(config.config_file_name)
except Exception:
    # If logging config is not present in alembic.ini, continue without it
    pass

# ensure app path is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extensions import db

# this is the MetaData object for 'autogenerate' support
target_metadata = db.metadata

# Ensure a sqlalchemy.url main option exists; fallback to local instance DB
if not config.get_main_option('sqlalchemy.url'):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    local_db = os.path.join(project_root, 'instance', 'baasket.db')
    config.set_main_option('sqlalchemy.url', f"sqlite:///{local_db}")


def run_migrations_offline():
    url = config.get_main_option('sqlalchemy.url')
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    url = config.get_main_option('sqlalchemy.url')
    connectable = engine_from_config(
        {'sqlalchemy.url': url},
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
