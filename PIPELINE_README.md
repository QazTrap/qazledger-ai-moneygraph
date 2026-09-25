# QazLedger MoneyGraph — Full Pipeline

Воспроизводимый AML pipeline для задания HackAlem AI.

## Входные данные

Положите в папку `data/`:

- `edges.parquet`
- `nodes.parquet`
- `transactions.parquet`

Папка `data/` не публикуется в GitHub.

## Установка

```bash
py -m pip install -r requirements.txt
```

## Запуск анализа

```bash
py pipeline/pipeline.py --data data --out output --top 20
```

## Результат

В папке `output/` создаются:

- `nodes_roles.csv`
- `clusters.csv`
- `top_nodes.csv`

## Реализовано

- роли:
  - `consolidator`
  - `transit`
  - `distributor`
  - `terminal`
  - `coordinator`
  - `peripheral`
- `role_score`
- `cluster_id`
- `priority_score`
- объяснимый `evidence`
- PageRank
- betweenness centrality
- Louvain-кластеризация с fallback
- Top-20+
- защита от ошибочной классификации узлов на границе `depth=4`
- отдельная обработка seed-узлов
- отсутствие hardcoded GID

## Проверенный результат

На предоставленном датасете HackAlem:

```text
nodes_roles.csv: 2248
clusters.csv: 91
top_nodes.csv: 20
```

Распределение ролей:

```text
terminal        1083
peripheral       767
consolidator     165
distributor      140
transit           47
coordinator       46
```

Проверки:

```text
empty evidence: 0
role_score outside 0..1: 0
priority_score outside 0..1: 0
empty cluster_id: 0
```

Локальное время полного прогона:

```text
~3.97 seconds
```

## Viewer

После выполнения pipeline создайте интерактивный Viewer:

```bash
py pipeline/viewer.py --data data --out output
```

Открыть на Windows:

```bash
start output/viewer.html
```

Viewer поддерживает:

- поиск любого GID;
- русский и английский интерфейс (`RU / EN`);
- роли узлов;
- `role_score`;
- `priority_score`;
- кластеры;
- объяснение `evidence`;
- входящие и исходящие связи;
- суммы и количество транзакций;
- направление движения средств;
- переход между соседними GID.

## Важно

`priority_score` — это приоритет для аналитической проверки, а не вероятность мошенничества.

MoneyGraph не определяет виновность человека или счёта. Финальное решение остаётся за AML-аналитиком.
