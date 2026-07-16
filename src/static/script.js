// --- RUNS ON EVERY PAGE LOAD ---
document.addEventListener("DOMContentLoaded", () => {
    const loginLink = document.getElementById("loginLink");
    const logoutButton = document.getElementById("logoutButton");
    
    // Check if user session exists in browser storage
    const sessionId = localStorage.getItem("session_id");

    if (sessionId) {
        // User is logged in: Show logout, hide login (SCRUM-263)
        if (loginLink) loginLink.classList.add("d-none");
        if (logoutButton) logoutButton.classList.remove("d-none");
    } else {
        // User is logged out: Show login, hide logout
        if (loginLink) loginLink.classList.remove("d-none");
        if (logoutButton) logoutButton.classList.add("d-none");
    }
});

// --- LOGIN FLOW ---
async function login() {
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;
    const messageElement = document.getElementById("message");

    messageElement.innerText = "";

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
            // Store token & redirect to home
            localStorage.setItem("session_id", data.session_id);
            window.location.href = "/home";
        } else {
            messageElement.innerText = data.message || "Login failed. Please try again.";
        }
    } catch (error) {
        console.error("Error during login:", error);
        messageElement.innerText = "An error occurred. Please check your connection.";
    }
}

// --- LOGOUT FLOW (SCRUM-264 to SCRUM-268) ---
async function logoutUser() {
    const sessionId = localStorage.getItem("session_id"); // Detect request (SCRUM-264)

    try {
        // Call Flask API to kill server-side session (SCRUM-265)
        const response = await fetch("/api/logout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId })
        });

        if (response.ok) {
            // Clear local security token (SCRUM-266)
            localStorage.removeItem("session_id");
            // Display logout confirmation (SCRUM-268)
            alert("You have successfully logged out!");
            // Redirect user to login page (SCRUM-267)
            window.location.href = "/login";
        } else {
            // Force logout client-side fallback if server fails
            localStorage.removeItem("session_id");
            window.location.href = "/login";
        }
    } catch (error) {
        console.error("Error during logout:", error);
        localStorage.removeItem("session_id");
        window.location.href = "/login";
    }
}