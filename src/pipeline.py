import os
import hashlib
import sqlite3
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


DB_PATH = os.getenv("DB_PATH", "/shared/sales.db")

SOURCES = {
    "products": os.getenv("PRODUCTS_URL")
    or os.getenv("PRODUCTS_SOURCE", "/app/data/produits.csv"),
    "stores": os.getenv("STORES_URL")
    or os.getenv("STORES_SOURCE", "/app/data/magasins.csv"),
    "sales": os.getenv("SALES_URL")
    or os.getenv("SALES_SOURCE", "/app/data/ventes.csv"),
}


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stores (
    store_id INTEGER PRIMARY KEY,
    city TEXT NOT NULL,
    employees INTEGER NOT NULL CHECK (employees >= 0)
);

CREATE TABLE IF NOT EXISTS products (
    product_ref TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id TEXT PRIMARY KEY,
    sale_date TEXT NOT NULL,
    product_ref TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    store_id INTEGER NOT NULL,
    FOREIGN KEY (product_ref) REFERENCES products(product_ref),
    FOREIGN KEY (store_id) REFERENCES stores(store_id)
);

CREATE TABLE IF NOT EXISTS analysis_results (
    analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT NOT NULL,
    dimension TEXT NOT NULL,
    metric_quantity INTEGER,
    metric_revenue NUMERIC,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def read_csv(source):
    if str(source).startswith(("http://", "https://")):
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        return pd.read_csv(StringIO(response.text))

    return pd.read_csv(source)


def sale_id(row):
    raw = (
        f"{row['sale_date']}|"
        f"{row['product_ref']}|"
        f"{int(row['quantity'])}|"
        f"{int(row['store_id'])}"
    )

    return hashlib.sha256(raw.encode()).hexdigest()


def main():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:

        # ---------------------------------------------------------------
        # Activation des clés étrangères
        # ---------------------------------------------------------------

        conn.execute("PRAGMA foreign_keys = ON;")

        # ---------------------------------------------------------------
        # Création du schéma
        # ---------------------------------------------------------------

        conn.executescript(SCHEMA)

        # ---------------------------------------------------------------
        # EXTRACT : lecture des fichiers CSV
        # ---------------------------------------------------------------

        stores = read_csv(SOURCES["stores"]).rename(
            columns={
                "ID Magasin": "store_id",
                "Ville": "city",
                "Nombre de salariés": "employees",
            }
        )

        products = read_csv(SOURCES["products"]).rename(
            columns={
                "Nom": "name",
                "ID Référence produit": "product_ref",
                "Prix": "price",
                "Stock": "stock",
            }
        )

        sales = read_csv(SOURCES["sales"]).rename(
            columns={
                "Date": "sale_date",
                "ID Référence produit": "product_ref",
                "Quantité": "quantity",
                "ID Magasin": "store_id",
            }
        )

        # ---------------------------------------------------------------
        # TRANSFORM : nettoyage et conversion des données
        # ---------------------------------------------------------------

        stores["store_id"] = stores["store_id"].astype(int)
        stores["employees"] = stores["employees"].astype(int)

        products["price"] = products["price"].astype(float)
        products["stock"] = products["stock"].astype(int)

        sales["sale_date"] = (
            pd.to_datetime(sales["sale_date"])
            .dt.strftime("%Y-%m-%d")
        )

        sales["quantity"] = sales["quantity"].astype(int)
        sales["store_id"] = sales["store_id"].astype(int)

        # ---------------------------------------------------------------
        # LOAD : rafraîchissement des tables de référence
        #
        # On ne fait PAS if_exists="replace".
        # Cela permet de conserver les contraintes PRIMARY KEY.
        # ---------------------------------------------------------------

        conn.execute("DELETE FROM sales")
        conn.execute("DELETE FROM stores")
        conn.execute("DELETE FROM products")

        stores.to_sql(
            "stores",
            conn,
            if_exists="append",
            index=False,
        )

        products.to_sql(
            "products",
            conn,
            if_exists="append",
            index=False,
        )

        # ---------------------------------------------------------------
        # LOAD : insertion des ventes
        # ---------------------------------------------------------------

        inserted = 0

        for row in sales.itertuples(index=False):

            data = {
                "sale_date": row.sale_date,
                "product_ref": row.product_ref,
                "quantity": row.quantity,
                "store_id": row.store_id,
            }

            current_sale_id = sale_id(pd.Series(data))

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO sales
                    (
                        sale_id,
                        sale_date,
                        product_ref,
                        quantity,
                        store_id
                    )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    current_sale_id,
                    row.sale_date,
                    row.product_ref,
                    row.quantity,
                    row.store_id,
                ),
            )

            inserted += cur.rowcount

        # ---------------------------------------------------------------
        # ANALYSE : suppression des anciens résultats
        # ---------------------------------------------------------------

        conn.execute("DELETE FROM analysis_results")

        # ---------------------------------------------------------------
        # ANALYSE : chiffre d'affaires total
        # ---------------------------------------------------------------

        conn.execute(
            """
            INSERT INTO analysis_results
                (
                    analysis_type,
                    dimension,
                    metric_quantity,
                    metric_revenue
                )
            SELECT
                'total_revenue',
                'ALL',
                SUM(s.quantity),
                SUM(s.quantity * p.price)
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            """
        )

        # ---------------------------------------------------------------
        # ANALYSE : ventes par produit
        # ---------------------------------------------------------------

        conn.execute(
            """
            INSERT INTO analysis_results
                (
                    analysis_type,
                    dimension,
                    metric_quantity,
                    metric_revenue
                )
            SELECT
                'by_product',
                p.product_ref,
                SUM(s.quantity),
                SUM(s.quantity * p.price)
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            GROUP BY p.product_ref
            """
        )

        # ---------------------------------------------------------------
        # ANALYSE : ventes par région / ville
        # ---------------------------------------------------------------

        conn.execute(
            """
            INSERT INTO analysis_results
                (
                    analysis_type,
                    dimension,
                    metric_quantity,
                    metric_revenue
                )
            SELECT
                'by_region',
                st.city,
                SUM(s.quantity),
                SUM(s.quantity * p.price)
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            JOIN stores st
                ON st.store_id = s.store_id
            GROUP BY st.city
            """
        )

        conn.commit()

        # ---------------------------------------------------------------
        # RESULTAT : chiffre d'affaires total
        # ---------------------------------------------------------------

        total = conn.execute(
            """
            SELECT ROUND(
                SUM(s.quantity * p.price),
                2
            )
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            """
        ).fetchone()[0]

        total = total or 0.0

        print()
        print("=" * 60)
        print("RESULTATS DU PIPELINE")
        print("=" * 60)

        print()
        print(f"Nouvelles lignes importées : {inserted}")
        print(f"Chiffre d'affaires total : {total:.2f} €")

        # ---------------------------------------------------------------
        # RESULTAT : ventes par produit
        # ---------------------------------------------------------------

        by_product = pd.read_sql_query(
            """
            SELECT
                p.product_ref AS produit,
                p.name AS nom,
                SUM(s.quantity) AS quantite_vendue,
                ROUND(
                    SUM(s.quantity * p.price),
                    2
                ) AS chiffre_affaires
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            GROUP BY
                p.product_ref,
                p.name
            ORDER BY chiffre_affaires DESC
            """,
            conn,
        )

        print()
        print("=" * 60)
        print("VENTES PAR PRODUIT")
        print("=" * 60)

        if by_product.empty:
            print("Aucune vente trouvée.")
        else:
            print(
                by_product.to_string(
                    index=False
                )
            )

        # ---------------------------------------------------------------
        # RESULTAT : ventes par région / ville
        # ---------------------------------------------------------------

        by_region = pd.read_sql_query(
            """
            SELECT
                st.city AS region,
                SUM(s.quantity) AS quantite_vendue,
                ROUND(
                    SUM(s.quantity * p.price),
                    2
                ) AS chiffre_affaires
            FROM sales s
            JOIN products p
                ON p.product_ref = s.product_ref
            JOIN stores st
                ON st.store_id = s.store_id
            GROUP BY st.city
            ORDER BY chiffre_affaires DESC
            """,
            conn,
        )

        print()
        print("=" * 60)
        print("VENTES PAR REGION")
        print("=" * 60)

        if by_region.empty:
            print("Aucune vente trouvée.")
        else:
            print(
                by_region.to_string(
                    index=False
                )
            )

        print()
        print("=" * 60)
        print("PIPELINE TERMINE AVEC SUCCES")
        print("=" * 60)
        print()


if __name__ == "__main__":
    main()



