CREATE DATABASE IF NOT EXISTS neorvion_iam
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON neorvion_iam.* TO 'neorvion'@'%';
FLUSH PRIVILEGES;
