-- One-time setup: a database and a user just for this app (run as root).
CREATE DATABASE IF NOT EXISTS travel_planner CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS travel_planner_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'travel_app'@'localhost' IDENTIFIED BY '<password from .env MYSQL_PASSWORD>';
CREATE USER IF NOT EXISTS 'travel_app'@'127.0.0.1' IDENTIFIED BY '<password from .env MYSQL_PASSWORD>';
GRANT ALL PRIVILEGES ON travel_planner.* TO 'travel_app'@'localhost', 'travel_app'@'127.0.0.1';
GRANT ALL PRIVILEGES ON travel_planner_test.* TO 'travel_app'@'localhost', 'travel_app'@'127.0.0.1';
FLUSH PRIVILEGES;
SELECT 'travel_planner database and travel_app user are ready' AS status;
