# 🐣 Young4ChickS – Poultry Brooder Management System

**Young4ChickS** is a Django-based web application designed to support an urban poultry brooder initiative targeting youth aged 18–30. The system enables Brooder Managers and Sales Representatives to manage chick stock, track farmer requests, allocate feeds, and monitor sales and payments efficiently.

---

## 🎯 Project Objectives

- Empower youth farmers through structured chick distribution and support.
- Provide clear workflows for chick requests, approvals, pickups, and feed allocations.
- Ensure traceability and accountability in stock, sales, and payments.
- Digitally track suppliers and manufacturers for all feed inputs.

---

## 🧩 Features

### 🧑‍💼 Role-Based Access
- **Brooder Manager**: Manages chick stock, approves/rejects farmer requests, adds feed stock, registers users, and oversees suppliers.
- **Sales Representative**: Registers farmers, submits chick requests, confirms pickups, and records payments.

### 🐥 Chick Management
- Submit and approve chick requests.
- Deduct stock upon physical pickup.
- Monitor chick aging and expiry.

### 🛍️ Feed Management
- Add feed stock from linked suppliers/manufacturers.
- Distribute feeds per farmer request.
- Record and view payment status.

### 🧾 Payment Tracking
- Split payments for chicks and feeds.
- Monitor pending vs. paid transactions.
- Generate sales reports.

### 📦 Supplier/Manufacturer Tracking
- Manage feed suppliers and manufacturers from dedicated interfaces.
- Link them to feed stock entries.

---

## ⚙️ Tech Stack

- **Backend:** Django 4.x (Python 3.12+)
- **Frontend:** HTML5, Bootstrap 4, JavaScript
- **Database:** SQLite (for development)

---

## 🚀 How to Run Locally

1. **Clone the Repository**
   ```bash
   git clone https://github.com/your-username/young4chicks.git
   cd young4chicks
2. **Create & Activate Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
4. **Run Migrations**
   ```bash
   python manage.py migrate
5. **Create Superuser**
   ```bash
   python manage.py createsuperuser
6. **Run Migrations**
   ```bash
   python manage.py migrate
7. **Start the Development Server**
   ```bash
   python manage.py runserver
8. **Visit in your browser:**
   ```bash
   (http://127.0.0.1:8000/)
---

## 📁 App Structure Overview
   

    home/ – Shared models like custom user roles
  
    sales/ – Handles farmer registration, chick requests, feed/payment logic
  
    manager/ – Dashboard, feed stock control, reporting, and user management
  
    templates/ – HTML templates grouped by role
  
    static/ – CSS, JS, and Bootstrap assets
---

## 📷 Screenshots
    Uploading these soon.
---

## 🧑‍🎓 Author
    Kakuru Peter Bingwa
    Software Engineering Student | Django Developer
    Project developed for academic submission and real-world implementation.
---

## 📄 License
    This project is for educational and demonstration purposes. Commercial rights are reserved by the author.
---
