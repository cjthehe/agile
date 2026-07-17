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



async function registerUser() {
  const name = document.getElementById('registerName').value;
  const email = document.getElementById('registerEmail').value;
  const password = document.getElementById('registerPassword').value;
  const confirmPassword = document.getElementById('registerConfirmPassword').value;
  const messageBox = document.getElementById('registerMessage');

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

async function createCounselor() {

    const response = await fetch(
        "/api/admin/create-counselor",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name: document.getElementById("name").value,
                email: document.getElementById("email").value,
                user_role: document.getElementById("role").value
            })
        }
    );

    const data = await response.json();

    document.getElementById("message").innerText = data.message;
}