CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL CHECK (length(full_name) BETWEEN 2 AND 100),
    email TEXT NOT NULL CHECK (length(email) BETWEEN 3 AND 150),
    phone TEXT NOT NULL CHECK (length(phone) BETWEEN 7 AND 30),
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    address TEXT NOT NULL DEFAULT '' CHECK (length(address) <= 250),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contacts_created_at ON contacts (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_category_id ON contacts (category_id);
