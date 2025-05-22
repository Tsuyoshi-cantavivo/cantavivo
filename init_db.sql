CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    name TEXT,
    age TEXT,
    contact TEXT,
    category TEXT,
    course TEXT,
    date TEXT,
    time TEXT,
    note TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contacts (
    id SERIAL PRIMARY KEY,
    name TEXT,
    email TEXT,
    message TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


