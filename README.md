# GoComet Assignment Backend

## Run the Flask app

Install dependencies:

```bash
pip install -r requirements.txt
```

Start MongoDB locally, then run:

```bash
flask run
```

Flask will read `.flaskenv` and `.env` automatically when `python-dotenv` is installed.

## Auto reload on code updates

`FLASK_DEBUG=1` is enabled in `.flaskenv`, so the development server reloads automatically whenever you change Python code.
