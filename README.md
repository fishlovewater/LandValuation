1. 開啟Docker Desktop
2. docker compose up -d
3. docker compose exec db psql -U 你的帳號 -d land_valuation
4. ALTER ROLE fish IN DATABASE land_valuation
5. SET search_path TO valuation, public;
6. \dt 可查詢database
