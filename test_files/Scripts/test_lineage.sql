-- Test SQL scripts for lineage analysis

-- Create base tables
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(100),
    created_date DATETIME
);

CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    customer_id INT,
    order_date DATETIME,
    total_amount DECIMAL(10,2),
    status VARCHAR(20)
);

CREATE TABLE order_items (
    item_id INT PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT,
    unit_price DECIMAL(10,2)
);

-- Create a view with column transformations
CREATE VIEW customer_orders AS
SELECT 
    c.customer_id,
    c.customer_name,
    c.email,
    COUNT(o.order_id) as total_orders,
    SUM(o.total_amount) as lifetime_value,
    MAX(o.order_date) as last_order_date
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.customer_name, c.email;

-- Create a complex view with CTEs
WITH monthly_sales AS (
    SELECT 
        customer_id,
        YEAR(order_date) as order_year,
        MONTH(order_date) as order_month,
        SUM(total_amount) as monthly_total
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id, YEAR(order_date), MONTH(order_date)
),
customer_metrics AS (
    SELECT 
        customer_id,
        COUNT(DISTINCT CONCAT(order_year, '-', order_month)) as active_months,
        AVG(monthly_total) as avg_monthly_spend
    FROM monthly_sales
    GROUP BY customer_id
)
SELECT 
    c.customer_id,
    c.customer_name,
    cm.active_months,
    cm.avg_monthly_spend,
    co.lifetime_value
FROM customers c
JOIN customer_metrics cm ON c.customer_id = cm.customer_id
JOIN customer_orders co ON c.customer_id = co.customer_id;

-- Insert with SELECT
INSERT INTO orders (order_id, customer_id, order_date, total_amount, status)
SELECT 
    ROW_NUMBER() OVER (ORDER BY c.customer_id) + 1000 as order_id,
    c.customer_id,
    GETDATE() as order_date,
    100.00 as total_amount,
    'pending' as status
FROM customers c
WHERE c.created_date >= DATEADD(day, -30, GETDATE());

-- Create a stored procedure
CREATE PROCEDURE UpdateCustomerMetrics
AS
BEGIN
    -- Update customer lifetime values
    UPDATE customers
    SET email = 'updated_' + email
    WHERE customer_id IN (
        SELECT customer_id 
        FROM orders 
        WHERE order_date >= DATEADD(day, -7, GETDATE())
    );
    
    -- Insert into audit table
    INSERT INTO audit_log (table_name, action, timestamp)
    VALUES ('customers', 'metrics_update', GETDATE());
END;
