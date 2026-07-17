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

    const logoutButton = document.getElementById('logoutButton');
    if (logoutButton) {
        logoutButton.addEventListener("click", async (event) => {
            event.preventDefault();
            await logout(event);
        });
    }
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

    messageBox.textContent = data.message;
    messageBox.className = "text-success mt-3 text-center";

    // Save email for verification
    localStorage.setItem("verification_email", data.user.email);

    // Hide registration card
    document
      .getElementById("registerCard")
      .classList.add("d-none");

    // Show verification card
    document
      .getElementById("verificationCard")
      .classList.remove("d-none");
  } catch (error) {
    messageBox.textContent = 'Registration failed';
    messageBox.className = 'text-danger mt-3 text-center';
  }
}

async function verifyEmail() {

    const email = localStorage.getItem("verification_email");

    const code = document
        .getElementById("verificationCode")
        .value;

    const message = document
        .getElementById("verificationMessage");

    try {

        const response = await fetch("/api/verify-email", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({

                email: email,

                verification_code: code

            })

        });

        const data = await response.json();

        if (response.ok) {

            message.textContent = data.message;
            message.className = "text-success mt-3 text-center";

            localStorage.removeItem("verification_email");

            setTimeout(() => {

                window.location.href = "/login";

            }, 2000);

        } else {

            message.textContent = data.message;
            message.className = "text-danger mt-3 text-center";

        }

    } catch (error) {

        message.textContent = "Verification failed.";
        message.className = "text-danger mt-3 text-center";

    }

}

// Handles user login submission
async function login() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const messageEl = document.getElementById('message');

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (response.ok) {
            // Save the session ID to local storage so the logout function can read it later
            localStorage.setItem('session_id', data.session_id);
            // Redirect smoothly to your home dashboard
            window.location.href = data.redirect;
        } else {
            messageEl.innerText = data.message || "Login failed.";
        }
    } catch (err) {
        messageEl.innerText = "An error occurred. Please try again.";
    }
}

// FIXED: Handles user logout execution and guarantees clean navigation redirection
async function logout(event) {
    // Prevent default anchor element navigational actions if triggered by one
    if (event) event.preventDefault();
    
    const sessionId = localStorage.getItem('session_id');

    try {
        const response = await fetch('/api/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });

        if (response.ok) {
            // Clear local tracking values seamlessly
            localStorage.removeItem('session_id');
            // Force return to the clean login state page
            window.location.href = '/login';
        } else {
            console.error("Logout failed at backend layer.");
            // Fallback redirect even if backend validation fails to protect client UX
            localStorage.removeItem('session_id');
            window.location.href = '/login';
        }
    } catch (err) {
        console.error("Network issue occurred executing logout API:", err);
        localStorage.removeItem('session_id');
        window.location.href = '/login';
    }
}

async function createCounselor() {
    const response = await fetch("/api/admin/create-counselor", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            name: document.getElementById("name").value,
            email: document.getElementById("email").value,
            role: document.getElementById("role").value
        })
    });

    const data = await response.json();
    const messageEl = document.getElementById("adminMessage");

    messageEl.innerText = data.message || "Unable to create counselor.";
    messageEl.className = response.ok ? "text-success mt-3 text-center" : "text-danger mt-3 text-center";
}
