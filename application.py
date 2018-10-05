import os
import requests

from flask import Flask, session, render_template, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker


app = Flask(__name__)

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")


@app.route("/")
def index():
    if 'user' not in session:
        return render_template("login.html")
    return render_template("index.html", logged=session['user'])


@app.route("/login", methods=["GET", "POST"])
def login():
    if 'user' in session:
        return render_template("index.html")
    if request.method == 'GET':
        return render_template("login.html")
    login = request.form.get("login")
    password = request.form.get("password")

    registered_user = db.execute("SELECT * FROM users WHERE login =:login AND password =:password",
                                 {"login": login, "password": password}).fetchone()
    if registered_user is None:
        return render_template("error.html", message="Login or Password is invalid.")
    else:
        session['user'] = login
        return render_template('index.html')


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == 'GET':
        return render_template("register.html")
    login = request.form.get("login")
    password = request.form.get("password")

    login_exist = db.execute("SELECT login FROM users WHERE login = :login",
                             {"login": login}).fetchone()
    if login_exist is not None:
        return render_template("error.html", message="This login is used.")
    db.execute("INSERT INTO users (login, password) VALUES (:login, :password)",
               {"login": login, "password": password})
    session['user'] = login
    db.commit()
    return render_template("success.html", message="You have successful registered.", seach="Find a book")


@app.route("/logout")
def logout():
    session.pop('user', None)
    return render_template("login.html")


@app.route("/books", methods=["POST", "GET"])
def find():
    """Find a book."""
    if 'user' not in session:
        return render_template("login.html")
    isbn = "'%" + request.form.get("book_isbn") + "%'"
    title = "'%" + request.form.get("book_title") + "%'"
    author = "'%" + request.form.get("book_author") + "%'"
    # Condition for select statement.
    like_conditions = []
    if isbn is not None:
        like_conditions.append("isbn LIKE " + isbn)
    if title is not None:
        like_conditions.append("title LIKE " + title)
    if author is not None:
        like_conditions.append("author LIKE " + author)
    # Select statement.
    select_statement = "SELECT * FROM books WHERE " + " AND ".join(like_conditions)

    # Find book/books.
    result = db.execute(select_statement)
    if result.rowcount == 0:
         return render_template("error.html", message="No books found.")
    books = result.fetchall()
    return render_template("books.html", books=books)


@app.route("/book/<isbn>", methods=["POST", "GET"])
def book(isbn):
    """Lists details about a single book."""
    if 'user' not in session:
        return render_template("login.html")
    if request.method == "POST":
        checked_rate = request.form.get("customRadioInline1")
        if checked_rate == "1":
            rate = "1"
        elif checked_rate == "2":
            rate = "2"
        elif checked_rate == "3":
            rate = "3"
        elif checked_rate == "4":
            rate = "4"
        else:
            rate = "5"
        review = request.form.get("note")
        book_id = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                             {"isbn": isbn}).fetchone()[0]
        if db.execute("SELECT review FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
                      {"user_id": session['user'], "book_id": book_id}).rowcount > 0:
            return render_template("error.html", message="You have leaved the review already.")
        db.execute("INSERT INTO reviews (review, rate, book_id, user_id) VALUES (:review, :rate, :book_id, :user_id)",
                   {"review": review, "rate": rate, "book_id": book_id, "user_id": session['user']})
        db.commit()

    book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                      {"isbn": isbn}).fetchone()
    book_id = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                         {"isbn": isbn}).fetchone()[0]
    reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id",
                        {"book_id": book_id}).fetchall()

    if db.execute("SELECT * FROM books WHERE id = :id",
                  {"id": book_id}).fetchone():
        res = requests.get("https://www.goodreads.com/book/review_counts.json",
                           params={"key": "HfaXwOMaXqAPmtvm2EwTew", "isbns": isbn})
        if res.status_code != 200:
            raise Exception("ERROR: API request unsuccessful.")
        data = res.json()

        average_rate = data["books"][0]["average_rating"]

        work_ratings_count = data["books"][0]["work_ratings_count"]

    return render_template("book.html", book=book, reviews=reviews, average_rate=average_rate,
                           work_ratings_count=work_ratings_count)


@app.route("/api/<string:isbn>")
def book_api(isbn):
    """Return details about a single book."""

    # Make sure book exists.
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                      {"isbn": isbn}).fetchone()
    if book is None:
        return jsonify({"error": "Invalid book's isbn"}), 404

    # Get all reviews.
    book_id = db.execute("SELECT id FROM books WHERE isbn = :isbn",
                         {"isbn": isbn}).fetchone()[0]
    reviews = db.execute("SELECT review FROM reviews WHERE book_id = :book_id",
                         {"book_id": book_id}).rowcount

    rates = db.execute("SELECT rate FROM reviews WHERE book_id = :book_id",
                           {"book_id": book_id}).fetchall()
    sum_rate = 0
    for rate in rates:
        sum_rate += rate[0]
    if reviews == 0:
        average_score = 0
    else:
        average_score = sum_rate / reviews

    return jsonify({
            "title": book.title,
            "author": book.author,
            "year": book.year,
            "isbn": book.isbn,
            "review_count": reviews,
            "average_score": average_score
        })