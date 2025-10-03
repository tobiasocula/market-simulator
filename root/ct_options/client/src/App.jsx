import { MyContextProvider } from "./context";
import Navbar from "./NavBar";
import TuneParams from "./TuneParams"
import {Routes, Route} from "react-router-dom";
import Overview from "./Overview";
import OrderBooks from "./OrderBooks";

function App() {
  return (
    <MyContextProvider>
      <Navbar />
      <Routes>
        <Route path="/" element={<TuneParams />} />
        <Route path="/orderbooks" element={<OrderBooks />} />
        <Route path="/overview" element={<Overview />} />
      </Routes>
    </MyContextProvider>
  );
}


export default App;