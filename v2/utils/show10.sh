#!/bin/bash

# Define the databases and their respective tables
DATABASES=(
    "gameEvents.db:gameEvents"
    "smsErrors.db:smsErrors"
    "playerTracking.db:playerTracking"
    "serverTracking.db:serverTracking"
)

# Directory where the databases are stored
DB_DIR="/path/to/your/working/directory"

# Function to show the last 10 rows of a given database and table
show_last_10_rows() {
    local db=$1
    local table=$2
    echo "Showing last 10 rows for $table in $db:"
    sqlite3 "$DB_DIR/$db" "SELECT * FROM $table ORDER BY id DESC LIMIT 10;"
    echo "--------------------------------------------"
}

# Iterate over each database and table and show the last 10 rows
for db_table in "${DATABASES[@]}"; do
    IFS=":" read -r db table <<< "$db_table"
    show_last_10_rows "$db" "$table"
done
