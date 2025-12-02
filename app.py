import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from datetime import datetime

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # --- PostgreSQL connection (works locally and on Heroku) ---
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Local development fallback
        from postgres import postgres_user, postgres_pass
        database_url = (
            f"postgresql://{postgres_user}:{postgres_pass}"
            f"@climate-db.croamw4iqxpi.us-east-2.rds.amazonaws.com:5432/climate_db"
        )
    
    # Heroku uses postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False  # Set to False for production

    db.init_app(app)

    # Define these OUTSIDE the app_context so routes can access them
    metadata = MetaData()
    table_names = []

    with app.app_context():
        try:
            # --- Reflect tables using metadata ---
            metadata.reflect(bind=db.engine, schema="public")
            table_names = [name.replace('public.', '') for name in metadata.tables.keys()]
            print(f"Reflected tables: {table_names}")
        except Exception as e:
            print(f"Error reflecting tables: {e}")

    # --- Home route ---
    @app.route("/")
    def home():
        if not table_names:
            return "<h1>No tables found!</h1><p>Check your database connection and credentials.</p>"

        html = "<h1>Climate Database API</h1>"
        html += "<p>Welcome to the Climate Database API. Available tables:</p><ul>"
        for table_name in table_names:
            full_name = f"public.{table_name}" if f"public.{table_name}" in metadata.tables else table_name
            table = metadata.tables[full_name]
            columns = [col.name for col in table.columns]
            col_list = ", ".join(columns[:5])  # Show first 5 columns
            if len(columns) > 5:
                col_list += "..."
            example_query = f"/{table_name}?limit=5"
            html += (
                f"<li><a href='/{table_name}'>{table_name}</a> "
                f"(columns: {col_list}) "
                f"<a href='{example_query}'>Example</a> | "
                f"<a href='/help/{table_name}'>Help</a></li>"
            )
        html += "</ul>"
        html += "<p>Use <code>/help/&lt;table&gt;</code> for column types and query instructions.</p>"
        return html

    # --- Help route ---
    @app.route("/help/<table_name>")
    def table_help(table_name):
        full_name = f"public.{table_name}" if f"public.{table_name}" in metadata.tables else table_name
        if full_name not in metadata.tables:
            return jsonify({"error": f"Table '{table_name}' not found"}), 404
        table = metadata.tables[full_name]
        cols = {col.name: col.type.python_type.__name__ for col in table.columns}
        
        return jsonify({
            "table": table_name,
            "columns": cols,
            "usage": {
                "base_url": f"/{table_name}",
                "parameters": {
                    "limit": "Number of results (default: 10)",
                    "offset": "Skip N results (for pagination)",
                    "<column_name>": "Filter by column value"
                },
                "example": f"/{table_name}?limit=5&offset=0"
            }
        })

    # --- Function factory for table routes ---
    def make_table_route(table_name, table_obj):
        def table_api():
            try:
                valid_cols = {col.name: col for col in table_obj.columns}
                filters = {}
                for key, value in request.args.items():
                    if key in ("limit", "offset"):
                        continue
                    if key not in valid_cols:
                        return jsonify({"error": f"Invalid filter: '{key}'"}), 400

                    col_type = valid_cols[key].type.python_type
                    try:
                        if col_type is bool:
                            converted = value.lower() == "true"
                        elif col_type is datetime:
                            converted = datetime.fromisoformat(value)
                        else:
                            converted = col_type(value)
                    except Exception:
                        return jsonify({
                            "error": f"Could not convert '{value}' to {col_type.__name__}"
                        }), 400

                    filters[key] = converted

                limit = int(request.args.get("limit", 10))
                offset = int(request.args.get("offset", 0))

                query = table_obj.select().limit(limit).offset(offset)
                for col_name, val in filters.items():
                    query = query.where(table_obj.c[col_name] == val)

                result = db.session.execute(query)
                rows = result.fetchall()
                data = [dict(row._mapping) for row in rows]

                return jsonify({
                    "table": table_name,
                    "count": len(data),
                    "limit": limit,
                    "offset": offset,
                    "filters": filters,
                    "results": data
                })

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        table_api.__name__ = f"table_api_{table_name}"
        return table_api

    # --- Add routes for all tables ---
    for table_name in table_names:
        full_name = f"public.{table_name}" if f"public.{table_name}" in metadata.tables else table_name
        table_obj = metadata.tables[full_name]
        app.add_url_rule(f"/{table_name}", view_func=make_table_route(table_name, table_obj))

    return app

# Create app instance at module level for gunicorn
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)