import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import pickle
import os

os.makedirs('model', exist_ok=True)
os.makedirs('data', exist_ok=True)

print("Step 1: Downloading dataset...")
url = "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv"
df = pd.read_csv(url)

print("Step 2: Preprocessing...")
df['TotalCharges'] = pd.to_numeric(df['TotalCharges'], errors='coerce')
df.dropna(inplace=True)
df.drop('customerID', axis=1, inplace=True)

le_dict = {}
for col in df.select_dtypes(include=['object']).columns:
    if col!= 'Churn':
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        le_dict[col] = le

df['Churn'] = df['Churn'].map({'Yes': 1, 'No': 0})

X = df.drop('Churn', axis=1)
y = df['Churn']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print("Step 3: Training model...")
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

accuracy = model.score(X_test, y_test) * 100
print(f"Model Accuracy: {accuracy:.2f}%")

with open('model/churn_model.pkl', 'wb') as f:
    pickle.dump(model, f)

with open('model/encoders.pkl', 'wb') as f:
    pickle.dump(le_dict, f)

df.to_csv('data/telco_churn.csv', index=False)
print("✅ Done: model/churn_model.pkl, model/encoders.pkl, data/telco_churn.csv")