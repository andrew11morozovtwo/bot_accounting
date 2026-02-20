#!/usr/bin/env python3
"""Скрипт очистки базы данных по имуществу (активы, операции, экземпляры, возвраты, категории).
Пользователи и логи не удаляются. Для проверки работоспособности на чистой базе."""
import sys
import os
import io
import argparse
import logging
import warnings

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.CRITICAL + 1)
for _ in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.base", "sqlalchemy.pool"):
    logging.getLogger(_).setLevel(logging.CRITICAL + 1)
os.environ["SQLALCHEMY_ECHO"] = "False"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import Config
from src.services.db import (
    get_db_engine,
    AssetReturnPhoto,
    Operation,
    AssetInstance,
    PendingReturn,
    Asset,
    Category,
)

# Используем свой engine/session, чтобы не трогать глобальный get_session
def clear_assets_data(dry_run: bool = False):
    engine = get_db_engine()
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        counts = {}
        # Порядок удаления по зависимостям (FK на assets)
        tables = [
            ("asset_return_photos", AssetReturnPhoto, None),
            ("operations", Operation, None),
            ("pending_returns", PendingReturn, None),
            ("asset_instances", AssetInstance, None),
            ("assets", Asset, None),
            ("categories", Category, None),
        ]
        for name, model, _ in tables:
            n = session.query(model).count()
            counts[name] = n
            if not dry_run and n > 0:
                session.query(model).delete()
        if not dry_run:
            session.commit()
        return counts
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def main():
    Config.DEV_MODE = False  # отключить вывод SQL
    parser = argparse.ArgumentParser(
        description="Очистка данных по имуществу (активы, операции, экземпляры, возвраты, категории). Пользователи не удаляются."
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Не спрашивать подтверждение",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет удалено, не удалять",
    )
    args = parser.parse_args()

    print(f"База данных: {Config.DB_PATH}")
    if not os.path.isfile(Config.DB_PATH):
        print("Файл БД не найден. Нечего очищать.")
        return 0

    counts = clear_assets_data(dry_run=True)
    total = sum(counts.values())
    if total == 0:
        print("Данные по имуществу уже пусты.")
        return 0

    print("\nБудет удалено:")
    for name, count in counts.items():
        if count > 0:
            print(f"  {name}: {count}")
    print(f"  Всего записей: {total}\n")

    if args.dry_run:
        print("Режим --dry-run: ничего не удалено.")
        return 0

    if not args.yes:
        try:
            answer = input("Продолжить? [y/N]: ").strip().lower()
        except EOFError:
            answer = "n"
        if answer not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return 0

    clear_assets_data(dry_run=False)
    print("Данные по имуществу удалены.")
    # Пересоздать таблицы и дефолтные категории при следующем запуске бота или явно
    print("При следующем запуске бота (или init_db) таблицы и категории по умолчанию будут в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
