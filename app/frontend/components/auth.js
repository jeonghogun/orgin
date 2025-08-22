/**
 * Authentication Component - Firebase Auth integration
 */
class AuthComponent {
    constructor() {
        this.auth = null;
        this.currentUser = null;
        this.loginButton = document.getElementById('login-button');
        this.logoutButton = document.getElementById('logout-button');
        this.userInfo = document.getElementById('user-info');
        
        this.initializeFirebase();
        this.initializeEventListeners();
    }
    
    initializeFirebase() {
        // Firebase configuration
        const firebaseConfig = {
            apiKey: "AIzaSyCfqSIsYaBGL9UXlrVCVF1dV-0g8qktX5Q",
            authDomain: "origin-project-12345.firebaseapp.com",
            projectId: "origin-project-12345",
            storageBucket: "origin-project-12345.appspot.com",
            messagingSenderId: "123456789012",
            appId: "1:123456789012:web:abcdef1234567890"
        };
        
        // Initialize Firebase
        firebase.initializeApp(firebaseConfig);
        this.auth = firebase.auth();
        

        
        // Set up auth state listener
        this.auth.onAuthStateChanged((user) => {
            this.handleAuthStateChange(user);
        });
    }
    
    initializeEventListeners() {
        this.loginButton.addEventListener('click', () => this.signIn());
        this.logoutButton.addEventListener('click', () => this.signOut());
    }
    
    handleAuthStateChange(user) {
        this.currentUser = user;
        
        if (user) {
            // User is signed in
            this.showUserInfo(user);
            this.setToken();
            
            // Clean URL and close review panel on login
            history.replaceState(null, '', '/');
            if (window.reviewPanel) {
                window.reviewPanel.closeReviewPanel();
            }
        } else {
            // User is signed out
            this.showLoginButton();
            localStorage.removeItem('idToken');
        }
    }
    
    async signIn() {
        try {
            const provider = new firebase.auth.GoogleAuthProvider();
            
            // Log redirect URI for debugging
            const redirectUri = `${window.location.origin}/__/auth/handler`;
            console.log('Firebase Auth redirect URI:', redirectUri);
            console.log('Current origin:', window.location.origin);
            console.log('Firebase project ID:', firebase.app().options.projectId);
            
            // Add custom parameters for debugging
            provider.setCustomParameters({
                prompt: 'select_account'
            });
            
            await this.auth.signInWithPopup(provider);
        } catch (error) {
            console.error('Sign in error:', error);
            console.error('Error details:', {
                code: error.code,
                message: error.message,
                email: error.email,
                credential: error.credential
            });
            alert('로그인에 실패했습니다.');
        }
    }
    
    async signOut() {
        try {
            await this.auth.signOut();
        } catch (error) {
            console.error('Sign out error:', error);
        }
    }
    
    async setToken() {
        if (this.currentUser) {
            try {
                const idToken = await this.currentUser.getIdToken();
                localStorage.setItem('idToken', idToken);
                console.log('Token set successfully');
            } catch (error) {
                console.error('Error getting token:', error);
            }
        }
    }
    
    showUserInfo(user) {
        this.loginButton.style.display = 'none';
        this.logoutButton.style.display = 'block';
        this.userInfo.style.display = 'block';
        
        this.userInfo.innerHTML = `
            <img src="${user.photoURL}" alt="Profile" class="user-avatar">
            <span>${user.displayName}</span>
        `;
    }
    
    showLoginButton() {
        this.loginButton.style.display = 'block';
        this.logoutButton.style.display = 'none';
        this.userInfo.style.display = 'none';
    }
    
    isAuthenticated() {
        return this.currentUser !== null;
    }
    
    getCurrentUser() {
        return this.currentUser;
    }
    
    async refreshToken() {
        if (this.currentUser) {
            await this.setToken();
        }
    }
}

// Export for global use
window.AuthComponent = AuthComponent;

