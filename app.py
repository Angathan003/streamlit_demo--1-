import streamlit as st

def main():
    st.title("Simple Streamlit Demo")
    st.write("Welcome to your first Streamlit app!")

    # Input text box
    user_input = st.text_input("Enter your name:")

    # Button to greet
    if st.button("Say Hello"):
        if user_input:
            st.success(f"Hello, {user_input}! 👋")
        else:
            st.error("Please enter your name first.")

    # Slider example
    age = st.slider("Select your age:", 0, 100, 25)
    st.write(f"Your age is: {age}")

    # Checkbox example
    if st.checkbox("Show more info"):
        st.write("This is a simple demo app using Streamlit.")

if __name__ == "__main__":
    main()
