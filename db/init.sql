-- Runs ONLY the first time the named volume is empty (docker-entrypoint-initdb.d behaviour).
CREATE TABLE IF NOT EXISTS products (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(120) NOT NULL UNIQUE,
    category          VARCHAR(60),
    compatible_models TEXT,
    price_idr         INTEGER NOT NULL CHECK (price_idr >= 0),
    quantity          INTEGER NOT NULL CHECK (quantity >= 0),
    location          VARCHAR(60) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO products (name, category, compatible_models, price_idr, quantity, location) VALUES
  ('Tempered Glass iPhone 13',  'Screen Protector', 'iPhone 13, iPhone 13 Pro', 25000, 40, 'Shelf A, Drawer 1'),
  ('Charger 20W USB-C',         'Charger',          'iPhone 12-15, Samsung',    85000, 12, 'Shelf B, Drawer 3'),
  ('Case Silicone Samsung A54', 'Case',             'Samsung Galaxy A54',       45000,  0, 'Shelf C, Box 2'),
  ('LCD Oppo A16',              'Spare Part',       'Oppo A16, A16s',          210000,  3, 'Cabinet 1, Tray 4')
ON CONFLICT (name) DO NOTHING;
