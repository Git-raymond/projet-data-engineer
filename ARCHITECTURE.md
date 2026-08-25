# Architecture

```text
CSV locaux ou URLs HTTP/HTTPS
            |
            v
+---------------------------+
| service app               |
| Python / pandas / requests|
| collecte + import + SQL   |
+-------------+-------------+
              |
              | volume Docker partagé
              | /shared/sales.db
              v
+---------------------------+
| service db                |
| SQLite 3                  |
| /data/sales.db            |
+---------------------------+
```

SQLite est une base embarquée et n'écoute pas sur un port réseau comme PostgreSQL.
La communication entre les deux conteneurs se fait donc ici par un volume Docker partagé.
Le service `app` dépend du healthcheck du service `db`.
