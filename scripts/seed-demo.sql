-- Demo data for a live run against a local SQL Server container: three databases and a read-only login.
-- Run once against a fresh container (tables are not dropped first):
--   docker cp scripts/seed-demo.sql <container>:/tmp/seed-demo.sql
--   docker exec <container> sh -c '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -b -v MCP_READER_PASSWORD="<password>" -i /tmp/seed-demo.sql'
IF DB_ID('shop_demo') IS NULL CREATE DATABASE shop_demo;
IF DB_ID('hr_demo') IS NULL CREATE DATABASE hr_demo;
IF DB_ID('blog_demo') IS NULL CREATE DATABASE blog_demo;
GO
USE shop_demo;
CREATE TABLE dbo.Customers (Id INT IDENTITY PRIMARY KEY, Email NVARCHAR(200) NOT NULL, FirstName NVARCHAR(100), LastName NVARCHAR(100), Country NVARCHAR(2));
CREATE TABLE dbo.Products (Id INT IDENTITY PRIMARY KEY, Name NVARCHAR(100) NOT NULL, Price DECIMAL(10,2) NOT NULL);
CREATE TABLE dbo.Orders (Id INT IDENTITY PRIMARY KEY, CustomerId INT NOT NULL REFERENCES dbo.Customers(Id), OrderedAt DATETIME2 NOT NULL, Total DECIMAL(10,2) NOT NULL);
CREATE TABLE dbo.OrderItems (Id INT IDENTITY PRIMARY KEY, OrderId INT NOT NULL REFERENCES dbo.Orders(Id), ProductId INT NOT NULL REFERENCES dbo.Products(Id), Qty INT NOT NULL);
INSERT dbo.Customers (Email,FirstName,LastName,Country) VALUES (N'anna@example.com',N'Anna',N'Ivanova','RU'),(N'john@example.com',N'John',N'Smith','US');
INSERT dbo.Products (Name,Price) VALUES (N'Keyboard',49.90),(N'Mouse',19.90);
INSERT dbo.Orders (CustomerId,OrderedAt,Total) VALUES (1,'2026-09-01',69.80),(2,'2026-09-02',19.90);
INSERT dbo.OrderItems (OrderId,ProductId,Qty) VALUES (1,1,1),(1,2,1),(2,2,1);
GO
CREATE PROCEDURE dbo.GetOrdersByCustomer @CustomerId INT AS SELECT Id, OrderedAt, Total FROM dbo.Orders WHERE CustomerId = @CustomerId;
GO
USE hr_demo;
CREATE TABLE dbo.Departments (Id INT IDENTITY PRIMARY KEY, Name NVARCHAR(100) NOT NULL);
CREATE TABLE dbo.Employees (Id INT IDENTITY PRIMARY KEY, DepartmentId INT NOT NULL REFERENCES dbo.Departments(Id), FullName NVARCHAR(200) NOT NULL, Email NVARCHAR(200), Salary DECIMAL(10,2), HiredOn DATE);
CREATE TABLE dbo.Vacations (Id INT IDENTITY PRIMARY KEY, EmployeeId INT NOT NULL REFERENCES dbo.Employees(Id), StartsOn DATE NOT NULL, Days INT NOT NULL);
INSERT dbo.Departments (Name) VALUES (N'Engineering'),(N'Sales');
INSERT dbo.Employees (DepartmentId,FullName,Email,Salary,HiredOn) VALUES (1,N'Petr Petrov',N'petr@example.com',5000,'2024-03-01'),(2,N'Maria Sidorova',N'maria@example.com',4200,'2025-01-15');
INSERT dbo.Vacations (EmployeeId,StartsOn,Days) VALUES (1,'2026-10-05',14),(2,'2026-11-01',7);
GO
USE blog_demo;
CREATE TABLE dbo.Authors (Id INT IDENTITY PRIMARY KEY, Name NVARCHAR(100) NOT NULL, Email NVARCHAR(200));
CREATE TABLE dbo.Posts (Id INT IDENTITY PRIMARY KEY, AuthorId INT NOT NULL REFERENCES dbo.Authors(Id), Title NVARCHAR(200) NOT NULL, Body NVARCHAR(MAX), PublishedAt DATETIME2);
CREATE TABLE dbo.Comments (Id INT IDENTITY PRIMARY KEY, PostId INT NOT NULL REFERENCES dbo.Posts(Id), Author NVARCHAR(100), Text NVARCHAR(500));
INSERT dbo.Authors (Name,Email) VALUES (N'Olga',N'olga@example.com'),(N'Ivan',N'ivan@example.com');
INSERT dbo.Posts (AuthorId,Title,Body,PublishedAt) VALUES (1,N'Hello',N'First post','2026-08-01'),(2,N'MCP notes',N'Read-only SQL','2026-08-10');
INSERT dbo.Comments (PostId,Author,Text) VALUES (1,N'guest',N'Nice'),(2,N'guest2',N'Useful');
GO
USE master;
IF SUSER_ID('mcp_reader') IS NULL CREATE LOGIN mcp_reader WITH PASSWORD = '$(MCP_READER_PASSWORD)', CHECK_POLICY = OFF;
GO
USE shop_demo; CREATE USER mcp_reader FOR LOGIN mcp_reader; ALTER ROLE db_datareader ADD MEMBER mcp_reader; GRANT VIEW DEFINITION TO mcp_reader;
GO
USE hr_demo; CREATE USER mcp_reader FOR LOGIN mcp_reader; ALTER ROLE db_datareader ADD MEMBER mcp_reader; GRANT VIEW DEFINITION TO mcp_reader;
GO
USE blog_demo; CREATE USER mcp_reader FOR LOGIN mcp_reader; ALTER ROLE db_datareader ADD MEMBER mcp_reader; GRANT VIEW DEFINITION TO mcp_reader;
GO
