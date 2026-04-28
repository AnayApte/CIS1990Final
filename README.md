# Penn Academic Co-Pilot — CIS 1990 Final Project

An AI-powered academic advisor for Penn SEAS students. Upload your transcript, describe your preferences, and get personalized course and schedule recommendations through a chat interface backed by live Penn Course Review data.

## How to Run

### 1. Install Python

Make sure you have Python 3.11 or later installed. You can check by running:

```
python3 --version
```

Download it from https://www.python.org/downloads/ if needed.

### 2. Open a terminal and navigate into the project folder

After unzipping the downloaded file:

```
cd CIS1990Final
```

### 3. Create a virtual environment and install dependencies

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows, replace the second line with:
```
venv\Scripts\activate
```

### 4. Add your OpenAI API key

Create a file named `.env` in the project folder with the following content:

```
OPENAI_API_KEY=your-key-here
```

Replace `your-key-here` with a real OpenAI API key.

### 5. Start the server

```
uvicorn server:app --reload
```

### 6. Open the app

Go to http://localhost:8000 in your browser. The chat interface will load automatically.

---
