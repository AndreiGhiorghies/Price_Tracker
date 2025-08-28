from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")  # servește index.html

@app.route("/product.html")
def product():
    # citește query string
    product_id = request.args.get("product_id")  # va fi string, ex: "1"
    
    # opțional: convertește la int
    if product_id is not None:
        product_id = int(product_id)
    
    # aici poți prelua informații din baza de date folosind product_id
    # ex: query SQLite

    return render_template("product.html", product_id=product_id)

if __name__ == "__main__":
    #app.run(host="0.0.0.0", port=5000, debug=True)  # debug=True doar în development
    app.run(debug=True)  # debug=True doar în development
