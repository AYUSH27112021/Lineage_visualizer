-- Create schema
CREATE SCHEMA IF NOT EXISTS scott;

-- Drop if exists
DROP TABLE IF EXISTS scott.emp CASCADE;
DROP TABLE IF EXISTS scott.dept CASCADE;

-- Create DEPT table
CREATE TABLE scott.dept (
    deptno NUMERIC(2,0) PRIMARY KEY,
    dname VARCHAR(14),
    loc VARCHAR(13)
);

-- Create EMP table
CREATE TABLE scott.emp (
    empno NUMERIC(4,0) PRIMARY KEY,
    ename VARCHAR(10),
    job VARCHAR(9),
    mgr NUMERIC(4,0),
    hiredate DATE,
    sal NUMERIC(7,2),
    comm NUMERIC(7,2),
    deptno NUMERIC(2,0) REFERENCES scott.dept(deptno),
    city VARCHAR(20)
);

-- Create VIEW vsal
CREATE OR REPLACE VIEW scott.vsal AS
SELECT 
    a.deptno AS Department,
    a.num_emp::NUMERIC / b.total_count AS Employees,
    a.sal_sum / b.total_sal AS Salary
FROM (
    SELECT deptno, COUNT(*) AS num_emp, SUM(sal) AS sal_sum
    FROM scott.emp
    WHERE city = 'NYC'
    GROUP BY deptno
) a,
(
    SELECT COUNT(*) AS total_count, SUM(sal) AS total_sal
    FROM scott.emp
    WHERE city = 'NYC'
) b;

-- Simulate INSERT ALL logic
INSERT INTO small_orders (oid, ottl, sid, cid)
SELECT o.order_id, o.order_total, o.sales_rep_id, o.customer_id
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_total < 100000;

INSERT INTO medium_orders (oid, ottl, sid, cid)
SELECT o.order_id, o.order_total, o.sales_rep_id, o.customer_id
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_total >= 100000 AND o.order_total < 200000;

INSERT INTO large_orders (oid, ottl, sid, cid)
SELECT o.order_id, o.order_total, o.sales_rep_id, o.customer_id
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_total >= 200000 AND o.order_total < 290000;

INSERT INTO special_orders (oid, ottl, sid, cid)
SELECT o.order_id, o.order_total, o.sales_rep_id, o.customer_id
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_total >= 290000;
