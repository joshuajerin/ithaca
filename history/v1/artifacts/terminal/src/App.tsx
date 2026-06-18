import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { AuthScreen } from "@/components/AuthScreen";
import NotFound from "@/pages/not-found";
import Terminal from "@/pages/Terminal";

const queryClient = new QueryClient();

function Router() {
  return (
    <Switch>
      <Route path="/" component={Terminal} />
      <Route component={NotFound} />
    </Switch>
  );
}

// Gates the whole app on authentication: a brief splash while we resolve the
// session cookie, the login/register screen when logged out, the terminal when
// authenticated.
function AuthGate() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="min-h-screen w-full bg-black text-white flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" strokeWidth={1.5} />
      </div>
    );
  }

  if (status === "anonymous") {
    return <AuthScreen />;
  }

  return <Router />;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <AuthProvider>
            <AuthGate />
          </AuthProvider>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
