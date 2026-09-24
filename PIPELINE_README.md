# QazLedger MoneyGraph — Full Pipeline

Добавляет воспроизводимый pipeline под исходное ТЗ HackAlem AI.

## Вход

Положите в папку `data/`:

- `edges.parquet`
- `nodes.parquet`
- `transactions.parquet`

## Установка

```bash
pip install -r requirements.txt
```

## Запуск

```bash
python pipeline/pipeline.py --data data --out output --top 20
```

## Выход

В `output/` создаются:

- `nodes_roles.csv`
- `clusters.csv`
- `top_nodes.csv`

## Реализовано

- роли `consolidator`, `transit`, `distributor`, `terminal`, `coordinator`, `peripheral`;
- `role_score`;
- `cluster_id`;
- `priority_score`;
- `evidence`;
- Louvain-кластеризация с fallback;
- Top-20+;
- учёт артефакта `depth=4`: отсутствие исходящих там не считается достаточным основанием для `terminal`.

## Важно

Код написан по схеме полей из ТЗ. Без исходных `.parquet` он ещё не проверен на реальном датасете HackAlem. После добавления данных нужно сделать тестовый прогон и при необходимости откалибровать пороги ролей.
