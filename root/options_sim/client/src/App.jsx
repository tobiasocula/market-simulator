import { MyContextProvider } from "./context";
import Navbar from "./NavBar";
import TuneParams from "./TuneParams"
import {Routes, Route} from "react-router-dom";
import Overview from "./Overview";
import OrderBooks from "./OrderBooks";
import Analysis from "./Analysis"

function App() {
  return (
    <MyContextProvider>
      <Navbar />
      <div
        style={{
          maxWidth: "1280px",
          margin: "0 auto",
          padding: "2rem",
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
          boxSizing: "border-box",
        }}
      >
        <Routes>
          <Route path="/" element={<TuneParams />} />
          <Route path="/orderbooks" element={<OrderBooks />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/analysis" element={<Analysis />} />
        </Routes>
      </div>
    </MyContextProvider>
  );
}

export default App;