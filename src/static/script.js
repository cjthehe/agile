// Centralized state manager for synchronization of Navbar controls
function updateAuthButtons() {
    const sessionId = localStorage.getItem('session_id');
    const loginLink = document.getElementById('loginLink');
    const logoutButton = document.getElementById('logoutButton');

    if (!loginLink || !logoutButton) {
        return;
    }

    if (sessionId) {
        loginLink.classList.add('d-none');
        logoutButton.classList.remove('d-none');
    } else {
        loginLink.classList.remove('d-none');
        logoutButton.classList.add('d-none');
    }
}

// Global initialization logic block run on page boot
document.addEventListener("DOMContentLoaded", () => {
    updateAuthButtons();
});

// User registration interface submission routine
async function registerUser() {
    const name = document.getElementById('registerName').value;
    const email = document.getElementById('registerEmail').value;
    const password = document.getElementById('registerPassword').value;
    const confirmPassword = document.getElementById('registerConfirmPassword').value;
    const messageBox = document.getElementById('registerMessage');

    if (!messageBox) return;

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password, confirmPassword })
        });

        const data = await response.json();

        if (!response.ok) {
            messageBox.textContent = data.message || 'Registration failed';
            messageBox.className = 'text-danger mt-3 text-center';
            return;
        }

        messageBox.textContent = `Registration successful. Welcome, ${data.user.name}!`;
        messageBox.className = 'text-success mt-3 text-center';
        
        const regForm = document.getElementById('registerForm');
        if (regForm) regForm.reset();
    } catch (error) {
        console.error("Error during registration:", error);
        messageBox.textContent = 'Registration failed';
        messageBox.className = 'text-danger mt-3 text-center';
    }
}

// User access validation login routine
async function login() {
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    const messageElement = document.getElementById("message");

    if (!messageElement) return;

    messageElement.innerText = "";
    messageElement.className = "mt-3 text-center text-danger";

    if (!email || !password) {
        messageElement.innerText = "Please enter both email and password.";
        return;
    }

    try {
        const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            localStorage.setItem("session_id", data.session_id);
            alert(data.message || "Login Successful!");
            
            // REDIRECTION FIX: Directs your successfully validated users 
            // directly onto the active hub instead of a generic home placeholder
            window.location.href = "/wellbeing";
        } else {
            messageElement.innerText = data.message || "Login failed. Please try again.";
        }
    } catch (error) {
        console.error("Error during login:", error);
        messageElement.innerText = "An error occurred. Please check your connection.";
    }
}

// Clears user sessions and handles secure logging out
async function logoutUser() {
    const sessionId = localStorage.getItem("session_id"); 

    try {
        await fetch("/api/logout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId })
        });
    } catch (error) {
        console.error("Error during server logout routing cleanup:", error);
    } finally {
        // Always destroy browser caching states and send users out safely
        localStorage.removeItem("session_id");
        window.location.href = "/login";
    }
}