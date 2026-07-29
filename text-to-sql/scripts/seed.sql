-- Create tables
CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    city VARCHAR(100),
    country VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    price DECIMAL(10,2),
    stock_quantity INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'pending',
    total_amount DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL
);

-- Create read-only user
CREATE USER readonly_user WITH PASSWORD 'readonly123';
GRANT CONNECT ON DATABASE ecommerce_db TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Seed data
INSERT INTO customers (name, email, city, country) VALUES
('Alice Johnson', 'alice@email.com', 'New York', 'USA'),
('Bob Smith', 'bob@email.com', 'London', 'UK'),
('Carol White', 'carol@email.com', 'Toronto', 'Canada'),
('David Lee', 'david@email.com', 'Sydney', 'Australia'),
('Eva Martinez', 'eva@email.com', 'Madrid', 'Spain'),
('Frank Brown', 'frank@email.com', 'Chicago', 'USA'),
('Grace Kim', 'grace@email.com', 'Seoul', 'South Korea'),
('Henry Wilson', 'henry@email.com', 'Berlin', 'Germany');

INSERT INTO products (name, category, price, stock_quantity) VALUES
('Laptop Pro 15', 'Electronics', 1299.99, 45),
('Wireless Mouse', 'Electronics', 29.99, 200),
('Office Chair', 'Furniture', 349.99, 30),
('Standing Desk', 'Furniture', 599.99, 15),
('Python Book', 'Books', 49.99, 100),
('USB-C Hub', 'Electronics', 79.99, 150),
('Monitor 27"', 'Electronics', 449.99, 60),
('Mechanical Keyboard', 'Electronics', 129.99, 80);

INSERT INTO orders (customer_id, order_date, status, total_amount) VALUES
(1, '2024-01-15', 'completed', 1329.98),
(2, '2024-01-20', 'completed', 449.99),
(3, '2024-02-01', 'completed', 679.98),
(1, '2024-02-14', 'completed', 49.99),
(4, '2024-02-20', 'shipped', 209.98),
(5, '2024-03-01', 'completed', 1299.99),
(6, '2024-03-10', 'pending', 349.99),
(7, '2024-03-15', 'completed', 579.98),
(8, '2024-03-20', 'shipped', 129.99),
(2, '2024-04-01', 'completed', 899.98);

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 1, 1299.99), (1, 2, 1, 29.99),
(2, 7, 1, 449.99),
(3, 3, 1, 349.99), (3, 6, 1, 79.99), (3, 5, 1, 49.99),
(4, 5, 1, 49.99),
(5, 2, 1, 29.99), (5, 6, 1, 79.99), (5, 7, 1, 449.99),
(6, 1, 1, 1299.99),
(7, 4, 1, 599.99), (7, 2, 1, 29.99), (7, 5, 1, 49.99),
(8, 8, 1, 129.99),
(9, 8, 1, 129.99),
(10, 7, 1, 449.99), (10, 3, 1, 349.99);